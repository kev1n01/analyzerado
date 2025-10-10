import requests
import base64
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Set
import time
from src.config import areasPathEDW,areasPathCOE, tagsCOE
import json
import pytz
from tzlocal import get_localzone
from src.helpers import setup_logger

logger = setup_logger('azure_devops_service')


class AzureDevOpsService:
    def __init__(self, url: str, pat: str):
        self.url = url
        self.headers = {
            'Accept': 'application/json',
            'Authorization': f'Basic {str(base64.b64encode(f":{pat}".encode("ascii")).decode("ascii"))}'
        }
        self.areaPathEDW = areasPathEDW
        self.areaPathCOE = areasPathCOE
        self.cache = {}
        self.cache_duration = 3600
        self.work_item_updates_cache = {}

    def get_team_projects(self) -> List[str]:
        """Get list of team projects"""
        try:
            url = f"{self.url}/_apis/projects?api-version=7.0"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return [project['name'] for project in response.json()['value']]
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error fetching team projects: {str(e)}")

    def _get_cache_key(self, func_name: str, *args) -> str:
        return f"{func_name}:{':'.join(str(arg) for arg in args)}"

    def _get_cached_result(self, func_name: str, *args) -> Any:
        key = self._get_cache_key(func_name, *args)
        if key in self.cache:
            cached = self.cache[key]
            if time.time() - cached['timestamp'] < self.cache_duration:
                return cached['result']
        return None

    def _cache_result(self, func_name: str, *args, result: Any):
        key = self._get_cache_key(func_name, *args)
        self.cache[key] = {
            'result': result,
            'timestamp': time.time()
        }
        return result

    def _get_unique_work_item_ids(self, team_projects: List[str], 
                                   work_item_types: List[str],
                                   start_date: datetime, 
                                   end_date: datetime) -> Set[int]:
        """Get unique work item IDs from all projects within date range"""
        unique_ids = set()
        current_date = start_date.date()
        end_date_only = end_date.date()
        
        # Convert to UTC for API calls
        local_tz = datetime.now().astimezone().tzinfo
        
        logger.info(f"Fetching unique work item IDs from {current_date} to {end_date_only}")
        
        while current_date <= end_date_only:
            # Create datetime at start of day in UTC
            day_start = datetime.combine(current_date, datetime.min.time())
            if day_start.tzinfo is None:
                day_start = day_start.replace(tzinfo=local_tz)
            day_start_utc = day_start.astimezone(timezone.utc)
            start_str = day_start_utc.strftime("%Y-%m-%dT%H:%M:%S")
            
            for project in team_projects:
                url = f"{self.url}/{project}/_apis/wit/reporting/workitemrevisions"
                params = {
                    'api-version': '7.1',
                    'startDateTime': start_str,
                    'fields': 'System.Id,System.WorkItemType'
                }
                
                try:
                    logger.info(f"Fetching revisions for {project} on {current_date}")
                    response = requests.get(url, headers=self.headers, params=params)
                    response.raise_for_status()
                    
                    data = response.json()
                    if 'values' in data:
                        for rev in data['values']:
                            fields = rev.get('fields', {})
                            wit = fields.get('System.WorkItemType')
                            
                            if wit in work_item_types:
                                work_item_id = fields.get('System.Id')
                                if work_item_id:
                                    unique_ids.add(work_item_id)
                    
                    time.sleep(0.1)  # Rate limiting
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error fetching revisions for {project} on {current_date}: {str(e)}")
                    continue
            
            current_date += timedelta(days=1)
        
        logger.info(f"Found {len(unique_ids)} unique work item IDs")
        return unique_ids

    def get_work_item_details(self, work_item_id: int) -> Dict:
        """Get current work item details"""
        try:
            url = f"{self.url}/_apis/wit/workitems/{work_item_id}"
            params = {
                'api-version': '7.1',
                'fields': 'System.Id,System.Title,System.WorkItemType,System.State,System.AreaPath,System.Tags,System.TeamProject'
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            fields = data.get('fields', {})
            
            return {
                'id': fields.get('System.Id'),
                'title': fields.get('System.Title'),
                'work_item_type': fields.get('System.WorkItemType'),
                'area_path': fields.get('System.AreaPath'),
                'tags': fields.get('System.Tags', ''),
                'team_project': fields.get('System.TeamProject')
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching details for work item {work_item_id}: {str(e)}")
            return {}

    def _extract_changed_by(self, update: Dict) -> str:
        """Extract the person who made the change from update"""
        revised_by = update.get('revisedBy', {})
        return revised_by.get('displayName', 'Unknown')

    def get_work_item_updates(self, work_item_id: int) -> List[Dict]:
        """Get all historical updates for a work item"""
        # Check cache first
        if work_item_id in self.work_item_updates_cache:
            cached = self.work_item_updates_cache[work_item_id]
            if time.time() - cached['timestamp'] < self.cache_duration:
                return cached['updates']
        
        try:
            url = f"{self.url}/_apis/wit/workitems/{work_item_id}/updates"
            params = {'api-version': '7.1', '$top': 200}
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            updates = data.get('value', [])
            
            # Get work item details to enrich updates
            wi_details = self.get_work_item_details(work_item_id)
            
            # Enrich each update with work item details
            for update in updates:
                update['_work_item_details'] = wi_details
            
            # Cache the result
            self.work_item_updates_cache[work_item_id] = {
                'updates': updates,
                'timestamp': time.time()
            }
            
            return updates
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching updates for work item {work_item_id}: {str(e)}")
            return []

    def analyze_state_changes(self, work_item_ids: Set[int], 
                             selected_states: List[str],
                             start_date: datetime, 
                             end_date: datetime) -> Dict[str, Dict]:
        """Analyze state changes from work item updates"""
        
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')
        
        local_tz = str(get_localzone())
        tz = pytz.timezone(local_tz)
        
        # Localize start and end
        if start_date.tzinfo is None:
            local_start = tz.localize(start_date)
        else:
            local_start = start_date.astimezone(tz)
            
        if end_date.tzinfo is None:
            local_end = tz.localize(end_date)
        else:
            local_end = end_date.astimezone(tz)
        
        start_utc = local_start.astimezone(timezone.utc)
        end_utc = local_end.astimezone(timezone.utc)
        
        state_analysis = {state: {'count': 0, 'items': []} for state in selected_states}
        processed_items = set()
        
        logger.info("=" * 50 + "START" + "=" * 50)
        
        for idx, work_item_id in enumerate(work_item_ids, 1):
            logger.info(f"Processing work item {idx}/{len(work_item_ids)}: ID {work_item_id}")
            
            updates = self.get_work_item_updates(work_item_id)
            
            for update in updates:
                fields = update.get('fields', {})
                
                # Check if there's a state change in this update
                state_change = fields.get('System.State')
                if not state_change:
                    continue
                
                new_state = state_change.get('newValue')
                if new_state not in selected_states:
                    continue
                
                # Get the state change date
                state_change_date_field = fields.get('Microsoft.VSTS.Common.StateChangeDate')
                if not state_change_date_field:
                    continue
                
                state_change_date_str = state_change_date_field.get('newValue')
                if not state_change_date_str:
                    continue
                
                # Parse the date
                try:
                    clean_date_str = state_change_date_str.replace('Z', '').split('.')[0]
                    state_date = datetime.strptime(clean_date_str, '%Y-%m-%dT%H:%M:%S')
                    state_date = state_date.replace(tzinfo=timezone.utc)
                except ValueError as e:
                    logger.error(f"Error parsing date {state_change_date_str}: {str(e)}")
                    continue
                
                is_within_range = start_utc <= state_date <= end_utc
                
                logger.info(
                    f"WID: {work_item_id} | Rev: {update.get('rev')} | "
                    f"State: {new_state} | Date: {state_date.strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"InRange: {is_within_range}"
                )
                
                if is_within_range:
                    item_key = (work_item_id, new_state, state_change_date_str)
                    
                    if item_key not in processed_items:
                        processed_items.add(item_key)
                        
                        # Get additional info from update or work item details
                        wi_details = update.get('_work_item_details', {})
                        
                        # Try to get from update first, then fall back to details
                        title = (update.get('fields', {}).get('System.Title', {}).get('newValue') 
                                or wi_details.get('title', 'N/A'))
                        old_state = state_change.get('oldValue', 'N/A')
                        work_item_type = (update.get('fields', {}).get('System.WorkItemType', {}).get('newValue')
                                        or wi_details.get('work_item_type', 'N/A'))
                        area_path = (update.get('fields', {}).get('System.AreaPath', {}).get('newValue')
                                   or wi_details.get('area_path', 'N/A'))
                        tags = (update.get('fields', {}).get('System.Tags', {}).get('newValue')
                              or wi_details.get('tags', ''))
                        team_project = wi_details.get('team_project', 'N/A')
                        changed_by = self._extract_changed_by(update)
                        
                        state_analysis[new_state]['count'] += 1
                        state_analysis[new_state]['items'].append({
                            'id': work_item_id,
                            'title': title,
                            'date': state_change_date_str,
                            'project': team_project,
                            'work_item_type': work_item_type,
                            'area_path': area_path,
                            'tags': tags,
                            'old_state': old_state,
                            'new_state': new_state,
                            'changed_by': changed_by
                        })
            
            time.sleep(0.05)  # Rate limiting
        
        logger.info("=" * 50 + "FINISH" + "=" * 50)
        return state_analysis

    def get_work_item_revisions(self, team_projects: List[str], work_item_types: List[str],
                                start_date: datetime, end_date: datetime) -> Dict:
        """Main method to get work item revisions by date range"""
        try:
            # Step 1: Get unique work item IDs
            work_item_ids = self._get_unique_work_item_ids(
                team_projects, 
                work_item_types,
                start_date, 
                end_date
            )
            
            return {
                'work_item_ids': work_item_ids,
                'start_date': start_date,
                'end_date': end_date,
                'total_unique_ids': len(work_item_ids)
            }
            
        except Exception as e:
            raise Exception(f"Error fetching work item revisions: {str(e)}")