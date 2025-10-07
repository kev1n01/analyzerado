import requests
import base64
from datetime import datetime, timezone
from typing import List, Dict, Any
import time
from src.config import areasPathCOE, areasPathEDW
import json

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

    def _execute_single_query(self, query: str) -> Dict:
        """Execute a single WIQL query"""
        url = f"{self.url}/_apis/wit/wiql?timePrecision=true&api-version=7.0"
        response = requests.post(url, json={"query": query}, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        print(f"Response to the Query:\n{json.dumps(data['workItems'], indent=4)}")
        print("=====================================================")
        return data

    def run_wiql_query(self, team_projects: List[str], work_item_types: List[str],
                      start_date: datetime, end_date: datetime) -> Dict:
        """Execute WIQL queries for each project with its specific conditions"""
        try:
            # get local timezone
            local_tz = datetime.now().astimezone().tzinfo

            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=local_tz)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=local_tz)

            start_utc = start_date.astimezone(timezone.utc)
            end_utc = end_date.astimezone(timezone.utc)

            start_str = start_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            end_str = end_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            # Create work item type condition
            type_condition = ", ".join([f"'{type}'" for type in work_item_types])
            
            # Base query structure
            base_query = """
            SELECT [System.Id]
            FROM WorkItems
            {project_specific_condition}
            AND [System.WorkItemType] IN ({type_condition})
            AND [Microsoft.VSTS.Common.StateChangeDate] >= '{start_str}'
            AND [Microsoft.VSTS.Common.StateChangeDate] <= '{end_str}'
            ORDER BY [System.Id]
            """.strip()
            
            # Combined results
            all_work_items = []
            queries = []
            
            # Execute separate queries for each project
            for project in team_projects:
                if project == "Enterprise Data Warehouse":
                    project_condition = f"""
            WHERE [System.TeamProject] = '{project}'
            AND [System.AreaPath] IN ({', '.join([f"'{areaedw}'" for areaedw in self.areaPathEDW])})
                    """
                elif project == "COE Operations":
                    project_condition = f"""
            WHERE [System.TeamProject] = '{project}'
            AND [System.AreaPath] IN ({', '.join([f"'{areacoe}'" for areacoe in self.areaPathCOE])})
            AND [System.Tags] CONTAINS 'DataOps'
                    """
                else:
                    project_condition = f"[System.TeamProject] = '{project}'"
                
                # Format and execute query for this project
                query = base_query.format(
                    project_specific_condition=project_condition,
                    type_condition=type_condition,
                    start_str=start_str,
                    end_str=end_str
                )
                queries.append(query)
                print(f"Executing query for {project}:", query)
                try:
                    result = self._execute_single_query(query)
                    if result and 'workItems' in result:
                        all_work_items.extend(result['workItems'])
                except requests.exceptions.RequestException as e:
                    print(f"Error executing query for {project}: {str(e)}")
                    continue  # Continue with next project if one fails
            
            # Return combined results in the same format
            return {'workItems': all_work_items, 'queries': queries}
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
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')

        # Make sure both are timezone-aware or timezone-naive
        if end_date.tzinfo is not None:
            end_date = end_date.replace(tzinfo=None)

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
                            print(f"Type start_date: {type(start_date)}")
                            print(f"Type state_date: {type(state_date)}")
                            print(f"Type end_date: {type(end_date)}")
                            print(f"{start_date} <=  {state_date} >= {end_date}")
                            print(start_date <= state_date <= end_date)
                            if start_date <= state_date <= end_date:
                                state_analysis[new_state]['count'] += 1
                                state_analysis[new_state]['items'].append({
                                    'id': work_item_id,
                                    'title': work_item['fields'].get('System.Title'),
                                    'date': state_date_str,
                                    'project': work_item['fields'].get('System.TeamProject'),
                                    'work_item_type': work_item['fields'].get('System.WorkItemType'),
                                    'area_path': work_item['fields'].get('System.AreaPath'),
                                    'tags': work_item['fields'].get('System.Tags', '')
                                })
        
        return state_analysis
