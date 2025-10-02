import streamlit as st
import os
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
import plotly.express as px
import json
from src.services.azure_devops_service import AzureDevOpsService

# Load environment variables
load_dotenv()

# Azure DevOps configuration
AZURE_DEVOPS_URL = os.getenv('AZURE_DEVOPS_URL')
AZURE_DEVOPS_PAT = os.getenv('AZURE_DEVOPS_PAT')

# Initialize Azure DevOps service
azure_service = AzureDevOpsService(AZURE_DEVOPS_URL, AZURE_DEVOPS_PAT)

# Streamlit UI
st.title("Azure DevOps Work Item State Analysis")

# Configuration section
st.header("Configuration")

col1, col2 = st.columns(2)

with col1:
    # Date range selection
    st.subheader("Date Range")
    end_date = st.date_input("End Date", datetime.now().date())
    start_date = st.date_input("Start Date", end_date.replace(day=1))  # First day of current month

    # Convert dates to datetime with time
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

with col2:
    # Team Project selection
    st.subheader("Team Projects")
    try:
        available_projects = azure_service.get_team_projects()
        selected_projects = st.multiselect(
            "Select Projects",
            available_projects,
            default=[available_projects[0]] if available_projects else None
        )
    except Exception as e:
        st.error(f"Error loading team projects: {str(e)}")
        selected_projects = []

# State and Work Item Type selection
col3, col4 = st.columns(2)

with col3:
    # State selection
    st.subheader("States to Analyze")
    all_states = [
        "New", "Active", "Resolved", "Closed",
        "3.1 - Ready for Test", "3.2 - In Progress",
        "3.3 - Failed Test", "3.4 - QA Approved"
    ]
    selected_states = st.multiselect(
        "Select States",
        all_states,
        default=["3.1 - Ready for Test", "3.4 - QA Approved"]
    )

with col4:
    # Work Item Types
    st.subheader("Work Item Types")
    work_item_types = st.multiselect(
        "Select Types",
        ["Bug", "Product Backlog Item", "User Story"],
        default=["Bug", "Product Backlog Item"]
    )

# Analysis button
analyze_button = st.button("Analyze Work Items", type="primary")

# Main content
if analyze_button and selected_states and selected_projects:
    # Show progress
    with st.spinner("Fetching work items..."):
        try:
            # Execute query
            query_results = azure_service.run_wiql_query(
                selected_projects,
                work_item_types,
                start_datetime,
                end_datetime
            )
            
            if query_results and 'workItems' in query_results:
                # Get work item IDs
                work_item_ids = [item['id'] for item in query_results['workItems']]
                
                if work_item_ids:
                    # Get work items details
                    work_items = azure_service.get_work_items(work_item_ids)
                    
                    # Analyze state changes
                    analysis_results = azure_service.analyze_state_changes(
                        work_items,
                        selected_states,
                        start_datetime,
                        end_datetime
                    )
                    
                    # Display results
                    st.header("Analysis Results")
                    
                    # Create summary DataFrame
                    summary_data = {
                        'State': [],
                        'Count': [],
                        'Details': []
                    }
                    
                    for state, data in analysis_results.items():
                        summary_data['State'].append(state)
                        summary_data['Count'].append(data['count'])
                        items_str = "\n".join([
                            f"ID: {item['id']} - {item['title']} ({item['project']})" 
                            for item in data['items']
                        ])
                        summary_data['Details'].append(items_str)
                    
                    df = pd.DataFrame(summary_data)
                    
                    # Display chart
                    if not df.empty:
                        fig = px.bar(df, x='State', y='Count',
                                   title="Work Items by State",
                                   labels={'Count': 'Number of Work Items', 'State': 'State'})
                        st.plotly_chart(fig)
                    
                    # Display detailed table
                    st.subheader("Detailed Results")
                    for state, data in analysis_results.items():
                        if data['count'] > 0:
                            with st.expander(f"{state} ({data['count']} items)"):
                                items_df = pd.DataFrame(data['items'])
                                st.dataframe(items_df)
                    
                    # Export button
                    export_data = {
                        'analysis_date': datetime.now().isoformat(),
                        'date_range': {
                            'start': start_date.isoformat(),
                            'end': end_date.isoformat()
                        },
                        'selected_states': selected_states,
                        'selected_projects': selected_projects,
                        'results': analysis_results
                    }
                    
                    st.download_button(
                        "Download JSON",
                        data=json.dumps(export_data, indent=2),
                        file_name="work_item_analysis.json",
                        mime="application/json"
                    )
                else:
                    st.warning("No work items found for the selected criteria.")
            else:
                st.error("Error fetching work items. Please check your configuration.")
        except Exception as e:
            st.error(f"Error during analysis: {str(e)}")
else:
    if not selected_states:
        st.warning("Please select at least one state to analyze.")
    if not selected_projects:
        st.warning("Please select at least one team project.")
