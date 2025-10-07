import streamlit as st
import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    layout="centered",
)

st.title("ADO Config Auth & Health Check")

# Sidebar for credentials
default_url = os.getenv("AZURE_DEVOPS_URL", "")
default_pat = os.getenv("AZURE_DEVOPS_PAT", "")

org_url = st.text_input("Organization URL", default_url, help="Example: https://dev.azure.com/your-org-name")
pat = st.text_input("Personal Access Token (PAT)", default_pat, type="password", help="Enter your Azure DevOps PAT")

# Main Section
st.divider()

if st.button("Check Health Status", width="stretch", icon=":material/health_cross:"):
    if not org_url or not pat:
        st.error("⚠️ Please enter both the organization URL and your Personal Access Token (PAT).")
    else:
        try:
            # Build headers
            token = base64.b64encode(f":{pat}".encode()).decode()
            headers = {
                "Accept": "application/json",
                "Authorization": f"Basic {token}"
            }

            # Organization-level health check endpoint
            url = f"{org_url}/_apis/projects?api-version=7.0"

            with st.spinner("Checking Azure DevOps API health..."):
                response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                project_count = data.get("count", "Unknown")

                if isinstance(project_count, int) and project_count > 0:
                    st.success("Azure DevOps API is **HEALTHY** and responding properly.", icon=":material/check_circle:")
                else:
                    st.warning(f"⚠️ Azure DevOps returned an unexpected response: **{project_count}**")

            else:
                st.error(f"❌ API returned status {response.status_code}: {response.text}")

        except requests.exceptions.RequestException as e:
            st.error(f"🚨 Connection error while contacting Azure DevOps API: {e}")
