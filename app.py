import streamlit as st
import requests
import os
from dotenv import load_dotenv
import base64

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
    url = f"{AZURE_DEVOPS_URL}/_apis/wit/wiql?api-version=7.0"
    data = {
        "query": query
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return f"Error: {response.status_code} - {response.text}"

# Streamlit UI
st.title("Azure DevOps Work Item Query")

# Text area for WIQL query input
query = st.text_area(
    "Enter your WIQL query:",
    """SELECT [System.Id], [System.Title], [System.State]
    FROM WorkItems
    WHERE [System.TeamProject] = 'Enterprise Data Warehouse'
    AND [System.WorkItemType] IN ('Bug','Product Backlog Item')
    AND [Microsoft.VSTS.Common.StateChangeDate] >= '2023-10-01'
    AND [Microsoft.VSTS.Common.StateChangeDate] <= '2023-10-31'
    """
)

# Button to execute query
if st.button("Run Query"):
    if query:
        results = run_wiql_query(query)
        st.json(results)
    else:
        st.error("Please enter a WIQL query")
