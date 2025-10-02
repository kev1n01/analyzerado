import requests
import os
import base64
from datetime import datetime
from typing import List, Dict, Any
import time

class AzureDevOpsService:
    def __init__(self, url: str, pat: str):
        self.url = url
        self.headers = {
            'Accept': 'application/json',
            'Authorization': f'Basic {str(base64.b64encode(f":{pat}".encode("ascii")).decode("ascii"))}'
        }
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

    def run_wiql_query(self, team_projects: List[str], work_item_types: List[str],
                      start_date: datetime, end_date: datetime) -> Dict:
        """Execute a WIQL query against Azure DevOps"""
        try:
            # Create project condition
            project_condition = " OR ".join([f"[System.TeamProject] = '{project}'" for project in team_projects])
            # Create work item type condition
            type_condition = ", ".join([f"'{type}'" for type in work_item_types])
            
            # Format dates in the correct format for WIQL (YYYY-MM-DD)
            start_str = start_date.strftime("'%Y-%m-%d'")
            end_str = end_date.strftime("'%Y-%m-%d'")
            
            query = f"""
            SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
                   [Microsoft.VSTS.Common.StateChangeDate], [System.TeamProject]
            FROM WorkItems
            WHERE ({project_condition})
            AND [System.WorkItemType] IN ({type_condition})
            AND [Microsoft.VSTS.Common.StateChangeDate] >= {start_str}
            AND [Microsoft.VSTS.Common.StateChangeDate] <= {end_str}
            ORDER BY [System.Id]
            """

            print("QUERRRRRRRRRRRY!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", query)

            url = f"{self.url}/_apis/wit/wiql?api-version=7.0"
            response = requests.post(url, json={"query": query}, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error executing WIQL query: {str(e)}")

    def get_work_items(self, ids: List[int]) -> List[Dict]:
        """Get work items details by IDs with batching"""
        cached = self._get_cached_result('get_work_items', ids)
        if cached:
            return cached

        try:
            batch_size = 200
            all_work_items = []
            
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i:i + batch_size]
                id_string = ','.join(map(str, batch_ids))
                url = f"{self.url}/_apis/wit/workitems?ids={id_string}&api-version=7.0"
                
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                
                batch_results = response.json()
                all_work_items.extend(batch_results.get('value', []))
                time.sleep(0.1)
            
            return self._cache_result('get_work_items', ids, result=all_work_items)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error fetching work items: {str(e)}")

    def get_work_item_updates(self, work_item_id: int) -> List[Dict]:
        """Get the update history of a work item"""
        cached = self._get_cached_result('get_work_item_updates', work_item_id)
        if cached:
            return cached

        try:
            url = f"{self.url}/_apis/wit/workitems/{work_item_id}/updates?api-version=7.0"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            updates = response.json().get('value', [])
            return self._cache_result('get_work_item_updates', work_item_id, result=updates)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error fetching work item updates for ID {work_item_id}: {str(e)}")

    def analyze_state_changes(self, work_items: List[Dict], selected_states: List[str],
                            start_date: datetime, end_date: datetime) -> Dict[str, Dict]:
        """Analyze state changes for work items within the date range"""
        state_analysis = {state: {'count': 0, 'items': []} for state in selected_states}
        
        for work_item in work_items:
            work_item_id = work_item['id']
            
            # Check historical states
            updates = self.get_work_item_updates(work_item_id)
            for update in updates:
                if 'fields' in update and 'System.State' in update['fields']:
                    new_state = update['fields']['System.State'].get('newValue')
                    if new_state in selected_states:
                        state_date_str = update.get('fields', {}).get(
                            'Microsoft.VSTS.Common.StateChangeDate', {}).get('newValue')
                        if state_date_str:
                            state_date = datetime.strptime(state_date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                            if start_date <= state_date <= end_date:
                                state_analysis[new_state]['count'] += 1
                                state_analysis[new_state]['items'].append({
                                    'id': work_item_id,
                                    'title': work_item['fields'].get('System.Title'),
                                    'date': state_date_str,
                                    'project': work_item['fields'].get('System.TeamProject')
                                })
        
        return state_analysis
