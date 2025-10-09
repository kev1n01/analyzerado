import requests
import base64
from datetime import datetime, timezone
from typing import List, Dict, Any
import time
from src.config import areasPathCOE, areasPathEDW
import json
import pytz
from tzlocal import get_localzone

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

    def get_work_item_revisions(self, team_projects: List[str], work_item_types: List[str],
                                start_date: datetime, end_date: datetime) -> Dict:
        """Get work item revisions using the reporting API"""
        try:
            # Get local timezone
            local_tz = datetime.now().astimezone().tzinfo
            
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=local_tz)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=local_tz)

            start_utc = start_date.astimezone(timezone.utc)
            end_utc = end_date.astimezone(timezone.utc)

            start_str = start_utc.strftime("%Y-%m-%dT%H:%M:%S")

            all_revisions = []
            
            print("==================================================START=================================================")
            # Execute separate queries for each project
            for project in team_projects:
                url = f"{self.url}/{project}/_apis/wit/reporting/workitemrevisions?api-version=7.1"
                
                # Add query parameters
                params = {
                    'startDateTime': start_str,
                    'fields': 'System.Id,System.Title,System.WorkItemType,System.State,System.AreaPath,System.Tags,System.TeamProject,Microsoft.VSTS.Common.StateChangeDate'
                }
                
                print(f"Fetching revisions for {project} from {start_str}")
                
                try:
                    response = requests.get(url, headers=self.headers, params=params)
                    response.raise_for_status()
                    
                    data = response.json()
                    if 'values' in data:
                        # Filter by work item type
                        filtered_revisions = [
                            rev for rev in data['values']
                            if rev.get('fields', {}).get('System.WorkItemType') in work_item_types
                        ]
                        all_revisions.extend(filtered_revisions)
                        print(f"Found {len(filtered_revisions)} revisions for {project}")
                        
                        desired_fields = [
                            "System.Id",
                            "System.Title",
                            "System.WorkItemType",
                            "System.State",
                            "System.AreaPath",
                            "System.Tags",
                            "System.TeamProject",
                            "Microsoft.VSTS.Common.StateChangeDate"
                        ]

                        filtered_items = []
                        for item in data['values']:
                            fields = item.get("fields", {})
                            filtered = {field: fields.get(field, None) for field in desired_fields}
                            filtered_items.append(filtered)
                        print(f"JSON data: {json.dumps(filtered_items, indent=2)}") 
                        
                except requests.exceptions.RequestException as e:
                    print(f"Error fetching revisions for {project}: {str(e)}")
                    continue
                
                time.sleep(0.1)
            
            return {
                'revisions': all_revisions,
                'start_date': start_utc,
                'end_date': end_utc
            }
        except Exception as e:
            raise Exception(f"Error fetching work item revisions: {str(e)}")

    def analyze_state_changes(self, revisions_data: Dict, selected_states: List[str],
                            start_date: datetime, end_date: datetime) -> Dict[str, Dict]:
        """Analyze state changes from revisions data"""
        state_analysis = {state: {'count': 0, 'items': []} for state in selected_states}
        
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')

        local_tz = str(get_localzone())
        tz = pytz.timezone(local_tz)
        
        # Localized start and end of day
        local_start = tz.localize(start_date)
        local_end = tz.localize(end_date)
        
        start_utc = local_start.astimezone(timezone.utc)
        end_utc = local_end.astimezone(timezone.utc)

        revisions = revisions_data.get('revisions', [])
        
        # Track processed work items to avoid duplicates
        processed_items = set()
        
        for revision in revisions:
            fields = revision.get('fields', {})
            work_item_id = fields.get('System.Id')
            current_state = fields.get('System.State')
            state_change_date_str = fields.get('Microsoft.VSTS.Common.StateChangeDate')
            
            # Skip if state is not in selected states
            if current_state not in selected_states:
                continue
            
            # Skip if no state change date
            if not state_change_date_str:
                continue
            
            # Parse the state change date
            clean_date_str = state_change_date_str.replace('Z', '').split('.')[0]
            state_date = datetime.strptime(clean_date_str, '%Y-%m-%dT%H:%M:%S')
            state_date = state_date.replace(tzinfo=timezone.utc)
            is_within_range = start_utc <= state_date <= end_utc
            
            print(f"RevId: {fields.get('rev')} | WITid: {work_item_id} | {datetime.strftime(start_utc,'%Y-%m-%d %H:%M:%S')} <=  {datetime.strftime(state_date,'%Y-%m-%d %H:%M:%S')} <= {datetime.strftime(end_utc,'%Y-%m-%d %H:%M:%S')} | {is_within_range}")
            # Check if state change falls within the date range
            if is_within_range:
                # Create unique key to avoid duplicate entries
                item_key = (work_item_id, current_state, state_change_date_str)
                
                if item_key not in processed_items:
                    processed_items.add(item_key)
                    
                    state_analysis[current_state]['count'] += 1
                    state_analysis[current_state]['items'].append({
                        'id': work_item_id,
                        'title': fields.get('System.Title'),
                        'date': state_change_date_str,
                        'project': fields.get('System.TeamProject'),
                        'work_item_type': fields.get('System.WorkItemType'),
                        'area_path': fields.get('System.AreaPath'),
                        'tags': fields.get('System.Tags', '')
                    })
        
        print("==================================================FINISH=================================================")
        
        return state_analysis