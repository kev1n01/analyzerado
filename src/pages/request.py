import streamlit as st
import requests
import os
from dotenv import load_dotenv
import base64
from tzlocal import get_localzone
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

def run_request(url):
    response = requests.get(url,headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        return f"Error: {response.status_code} - {response.text}"

# ---------------------- Streamlit UI ----------------------

st.title("Azure DevOps request builder")

# Detect local timezone automatically
local_tz = str(get_localzone())

st.badge(f"Your timezone: **{local_tz}**", icon=":material/globe_location_pin:")

st.caption("""
**Usage Notes:**
- Adjust `startDateTime` to filter results
- Select only needed fields for better performance
- Check the documentation link above for additional parameters [Azure DevOps Reporting Work Item Revisions API](https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/reporting-work-item-revisions/read-reporting-revisions-get?view=azure-devops-rest-7.2&tabs=HTTP)
""")

query = st.text_area("Enter url request:", f"{AZURE_DEVOPS_URL}/_apis/wit/reporting/workitemrevisions?api-version=7.1&startDateTime=2025-10-07T00:00:00")

# Button to execute query
if st.button("Run request"):
    if query.strip():
        results = run_request(query)
        if isinstance(results, dict) and "values" in results:
            work_items = results["values"]

            # Campos que quieres mostrar
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

            # Extrae solo los campos deseados
            filtered_items = []
            for item in work_items:
                fields = item.get("fields", {})
                filtered = {field: fields.get(field, None) for field in desired_fields}
                filtered_items.append(filtered)

            st.success(f"Found {len(filtered_items)} work items.")
            st.json(filtered_items)

        else:
            st.error(results)
    else:
        st.error("Please enter url request")

