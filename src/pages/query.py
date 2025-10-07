import streamlit as st
import requests
import os
from dotenv import load_dotenv
import base64
from datetime import datetime
from tzlocal import get_localzone
import json
from src.helpers import convert_dates_to_utc
# Load environment variables
load_dotenv()

# Azure DevOps configuration
AZURE_DEVOPS_URL = os.getenv('AZURE_DEVOPS_URL')
AZURE_DEVOPS_PAT = os.getenv('AZURE_DEVOPS_PAT')

# Create Basic Auth header with PAT
authorization = str(base64.b64encode(f":{AZURE_DEVOPS_PAT}".encode('ascii')).decode('ascii'))

# Configure headers for Azure DevOps API
headers = {
    'Accept': 'application/json',
    'Authorization': f'Basic {authorization}'
}

def run_wiql_query(query):
    """Execute a WIQL query against Azure DevOps"""
    url = f"{AZURE_DEVOPS_URL}/_apis/wit/wiql?timePrecision=true&api-version=7.0"
    data = {"query": query}
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Executing query:", query)
        print(f"Response to the Query Builder:\n{json.dumps(data['workItems'], indent=4)}")
        return data
    else:
        return f"Error: {response.status_code} - {response.text}"

# ---------------------- Streamlit UI ----------------------

st.title("Azure DevOps WIQL Query")

# Detect local timezone automatically
local_tz = str(get_localzone())

st.badge(f"Your timezone: **{local_tz}**", icon=":material/globe_location_pin:")

# Text area for WIQL query
default_query = f"""
SELECT [System.Id]
FROM WorkItems
WHERE [System.TeamProject] = 'Enterprise Data Warehouse'

AND [System.AreaPath] IN ('Enterprise Data Warehouse\\EDW Team 1','Enterprise Data Warehouse\\EDW Team 2')

AND [System.WorkItemType] IN ('Bug','Product Backlog Item')
AND [Microsoft.VSTS.Common.StateChangeDate] >= '{datetime.now().date()}'
AND [Microsoft.VSTS.Common.StateChangeDate] <= '{datetime.now().date()}'

ORDER BY [System.Id]
""".strip()

query = st.text_area("Enter your WIQL query:", default_query, height="content")

# Button to execute query
if st.button("Run Query"):
    if query.strip():
        # Convert date-only filters to UTC datetimes
        converted_query = convert_dates_to_utc(query, local_tz)

        with st.expander("Query after UTC conversion"):
          st.code(converted_query, language="sql")

        results = run_wiql_query(converted_query)

        if isinstance(results, dict) and "workItems" in results:
            st.success(f"Found {len(results['workItems'])} work items.")
            st.json({'workItems': results['workItems']})
        else:
            st.error(results)
    else:
        st.error("Please enter a WIQL query")
