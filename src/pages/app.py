import streamlit as st
import os
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
from src.services.azure_devops_service import AzureDevOpsService
from src.config import all_states, all_work_item_types
from tzlocal import get_localzone
import time

# Load environment variables
load_dotenv()

# Azure DevOps configuration
AZURE_DEVOPS_URL = os.getenv('AZURE_DEVOPS_URL')
AZURE_DEVOPS_PAT = os.getenv('AZURE_DEVOPS_PAT')

# Initialize Azure DevOps service
azure_service = AzureDevOpsService(AZURE_DEVOPS_URL, AZURE_DEVOPS_PAT)

# Streamlit UI
local_tz = datetime.now().astimezone().tzinfo
st.title(f"Analyzer WITs ADO")

# Configuration section
st.set_page_config(layout="wide")
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Date range selection
    # st.subheader("Date Range")
    st.badge(f"Timezone: (UTC{local_tz}:00) {str(get_localzone())} ", icon=":material/globe_location_pin:")
    start_date = st.date_input("Start Date", datetime.now().date())
    end_date = st.date_input("End Date", datetime.now().date())

    # Convert dates to datetime with time
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

with col2:
    # Team Project selection
    try:
        available_projects = azure_service.get_team_projects()
        selected_projects = st.multiselect(
            "Select Team Projects",
            available_projects,
            default=[available_projects[0],available_projects[1]] if available_projects else None
        )
    except Exception as e:
        st.error(f"Error loading team projects: {str(e)}")
        selected_projects = []

# State and Work Item Type selection
with col3:
    # State selection
    selected_states = st.multiselect(
        "Select States",
        all_states,
        default=["3.1 - Ready for Test", "3.4 - QA Approved"]
    )

with col4:
    # Work Item Types
    work_item_types = st.multiselect(
        "Select Work Item Types",
        all_work_item_types,
        default=["Bug", "Product Backlog Item"]
    )

# Analysis button
analyze_button = st.button("Go Analyze", type="primary", width="stretch", help="Click to start analyze",icon=":material/rocket_launch:")

if 'run_download' not in st.session_state:
    st.session_state.run_download = False

# Main content
if analyze_button and selected_states and selected_projects and work_item_types:
    # Show progress
    st.session_state.run_download = True

    try:
        # Execute query
        query_results = azure_service.run_wiql_query(
            selected_projects,
            work_item_types,
            start_datetime,
            end_datetime
        )

        if st.session_state.run_download:
          with st.status("Searching work items...", expanded=True) as status:
              st.write(f"{len(query_results['workItems'])} work items found.")
              time.sleep(2)
              st.write("Analyzing state changes...")
              time.sleep(2)
              st.write("Save results...")

        with st.expander("Query after UTC conversion"):
          for q in query_results['queries']:
            st.code(q, language="sql")

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
                
                # Prepare data for analysis
                all_items = []
                state_project_counts = {}

                for state, data in analysis_results.items():
                    for item in data['items']:
                        # Add to all items list
                        all_items.append({
                            'ID': f"{AZURE_DEVOPS_URL}/{item['project']}/_workitems/edit/{item['id']}",
                            'Title': item['title'],
                            'State': state,
                            # 'Project': item['project'],
                            'Type': item.get('work_item_type', ''),
                            'Area Path': item.get('area_path', ''),
                            'Tags': item.get('tags', ''),
                            'State Change Date': pd.to_datetime(item['date']).strftime('%m/%d/%Y %H:%M'),
                            'SCD UTC': pd.to_datetime(item['date']).strftime('%m/%d/%Y %H:%M')
                        })
                        
                        # Count for cross table
                        project = item['project']
                        if project not in state_project_counts:
                            state_project_counts[project] = {}
                        if state not in state_project_counts[project]:
                            state_project_counts[project][state] = 0
                        state_project_counts[project][state] += 1

                # Create and display cross table
                if state_project_counts:
                    st.divider()
                    st.subheader("State Count by Project")
                    
                    # Get unique states
                    all_states = sorted(list(set(
                        state 
                        for project_counts in state_project_counts.values() 
                        for state in project_counts.keys()
                    )))
                    
                    # Create DataFrame for cross table
                    cross_table_data = []
                    for project in state_project_counts:
                        row = {'Project': project}
                        for state in all_states:
                            row[state] = state_project_counts[project].get(state, 0)
                        cross_table_data.append(row)
                    
                    cross_df = pd.DataFrame(cross_table_data)
                    
                    # Add total row and column
                    cross_df['Total'] = cross_df[all_states].sum(axis=1)
                    total_row = pd.DataFrame([{
                        'Project': 'Total',
                        **{state: cross_df[state].sum() for state in all_states},
                        'Total': cross_df['Total'].sum()
                    }])
                    cross_df = pd.concat([cross_df, total_row])

                # Display detailed table
                if all_items:
                    status.update(
                        label="Analysis complete!", state="complete", expanded=False
                    )
                    st.session_state.run_download = False 
                    df = pd.DataFrame(all_items)
                    # Reorder columns
                    df = df[['ID', 'Title', 'Type', 'State', 'State Change Date', 'SCD UTC']]
                    
                    # Configure the dataframe display
                    # Display cross table
                    st.dataframe(
                        cross_df,
                        hide_index=True,
                        column_config={
                            "Project": st.column_config.Column(
                                "Project",
                                width="medium",
                                pinned="left"
                            )
                        }
                    )
                    st.subheader("Detailed Results")
                    df = pd.DataFrame(all_items)
                    # Reorder columns
                    df = df[['ID', 'Title', 'Type', 'State', 'Area Path', 'Tags', 'State Change Date', 'SCD UTC']]
                    
                    # Configure the dataframe display
                    st.dataframe(
                        df,
                        hide_index=True,
                        column_config={
                            "ID": st.column_config.LinkColumn(
                                "ID",
                                width="small",
                                pinned="left",
                                help="Go to work item ADO",
                                display_text=r"(\d+)$"
                            ),
                            "State Change Date": st.column_config.DatetimeColumn(
                                "State Change Date",
                                timezone=str(get_localzone()),
                                format="MM/DD/YYYY HH:mm",
                                width="medium"
                            ),
                            "SCD UTC": st.column_config.DatetimeColumn(
                                "SCD UTC",
                                format="MM/DD/YYYY HH:mm",
                                width="medium"
                            ),
                            "Area Path": st.column_config.Column(
                                "Area Path",
                                width="medium"
                            ),
                            "Tags": st.column_config.Column(
                                "Tags",
                                width="medium"
                            )
                        }
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
    if not work_item_types:
        st.warning("Please select at least one work item type.")
