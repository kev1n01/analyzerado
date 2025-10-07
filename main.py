import streamlit as st
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Azure DevOps configuration
AZURE_DEVOPS_URL = os.getenv('AZURE_DEVOPS_URL')
AZURE_DEVOPS_PAT = os.getenv('AZURE_DEVOPS_PAT')

# Sidebar
with st.sidebar:
    st.subheader("Config Credentials")
    st.text_input("Organitazion URL", AZURE_DEVOPS_URL, help="Enter your orgnization url")
    st.text_input("PAT", AZURE_DEVOPS_PAT, type="password", help="Enter your personal access token")

pg = st.navigation([
    st.Page("src/pages/app.py", title="Analyzer", icon=":material/wand_stars:"), 
    st.Page("src/pages/query.py", title="Query Builder", icon=":material/search_gear:", url_path="/query-builder")
])
pg.run()
