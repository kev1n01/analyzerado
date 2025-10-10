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
st.title(f"Analyzer WITs ADO - Historical Analysis")
st.badge(f"Timezone: ({local_tz}) {str(get_localzone())} ", icon=":material/globe_location_pin:")


# Initialize session state for caching results
if 'analysis_df' not in st.session_state:
    st.session_state.analysis_df = None
if 'cross_df' not in st.session_state:
    st.session_state.cross_df = None

# Configuration section
st.set_page_config(layout="wide")
col1, col2, col3, col4 = st.columns(4)

with col1:
    start_date = st.date_input("Start Date", datetime.now().date(), format="MM/DD/YYYY")
    end_date = st.date_input("End Date", datetime.now().date(), format="MM/DD/YYYY")

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
            default=[available_projects[0], available_projects[1]] if len(available_projects) >= 2 else available_projects
        )
    except Exception as e:
        st.error(f"Error loading team projects: {str(e)}")
        selected_projects = []

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
analyze_button = st.button("Go Analyze", type="primary", width="stretch", help="Click to start analyze", icon=":material/rocket_launch:")

if analyze_button and selected_states and selected_projects and work_item_types:
    try:
        with st.status("Fetching work item revisions...", expanded=True) as status:
            st.write("Step 1: Retrieving unique work item IDs from Azure DevOps...")
            
            # Get unique work item IDs from all days in range
            revisions_data = azure_service.get_work_item_revisions(
                selected_projects,
                work_item_types,
                start_datetime,
                end_datetime
            )
            
            total_ids = revisions_data['total_unique_ids']
            st.write(f"✓ Found {total_ids} unique work items")
            time.sleep(1)
            
            st.write("Step 2: Fetching historical updates for each work item...")
            progress_bar = st.progress(0)
            
            # This will fetch updates with caching
            work_item_ids = revisions_data['work_item_ids']
            for idx, wi_id in enumerate(work_item_ids):
                azure_service.get_work_item_updates(wi_id)
                progress_bar.progress((idx + 1) / total_ids)
            
            st.write("✓ Updates retrieved and cached")
            time.sleep(1)
            
            st.write("Step 3: Analyzing state changes within date range...")
            
            # Analyze state changes
            analysis_results = azure_service.analyze_state_changes(
                work_item_ids,
                selected_states,
                start_datetime,
                end_datetime
            )
            
            time.sleep(1)
            st.write("Preparing results...")
            time.sleep(1)
            
            status.update(
                label="Analysis complete!", state="complete", expanded=False
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
                    'Old State': item.get('old_state', 'N/A'),
                    'Type': item.get('work_item_type', ''),
                    'Area Path': item.get('area_path', ''),
                    'Tags': item.get('tags', ''),
                    'Changed By': item.get('changed_by', 'Unknown'),
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

        # Display cross table
        if state_project_counts:
            st.divider()
            st.subheader("State Count by Project")
            
            # Get unique states
            unique_states = sorted(list(set(
                state 
                for project_counts in state_project_counts.values() 
                for state in project_counts.keys()
            )))
            
            # Create DataFrame for cross table
            cross_table_data = []
            for project in state_project_counts:
                row = {'Project': project}
                for state in unique_states:
                    row[state] = state_project_counts[project].get(state, 0)
                cross_table_data.append(row)
            
            cross_df = pd.DataFrame(cross_table_data)
            
            # Add total row and column
            cross_df['Total'] = cross_df[unique_states].sum(axis=1)
            total_row = pd.DataFrame([{
                'Project': 'Total',
                **{state: cross_df[state].sum() for state in unique_states},
                'Total': cross_df['Total'].sum()
            }])
            cross_df = pd.concat([cross_df, total_row], ignore_index=True)
            
            # Store in session state
            st.session_state.cross_df = cross_df
            
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

        # Display detailed table
        if all_items:
            st.divider()
            st.subheader("Detailed Results")
            
            df = pd.DataFrame(all_items)
            df = df[['ID', 'Title', 'Type', 'Old State', 'State', 'Area Path', 'Tags', 'Changed By', 'State Change Date', 'SCD UTC']]
            
            # Store in session state
            st.session_state.analysis_df = df
            
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
                        "State Change Date (Local)",
                        timezone=str(get_localzone()),
                        format="MM/DD/YYYY HH:mm:ss",
                        width="medium"
                    ),
                    "SCD UTC": st.column_config.DatetimeColumn(
                        "State Change Date (UTC)",
                        format="MM/DD/YYYY HH:mm:ss",
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
            st.warning("No state changes found for the selected criteria.")

    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        import traceback
        st.error(traceback.format_exc())

# Display cached results if available (when not running new analysis)
elif st.session_state.analysis_df is not None and not analyze_button:
    st.divider()
    st.subheader("Last Analysis Results")
    
    if st.session_state.cross_df is not None:
        st.subheader("State Count by Project")
        st.dataframe(
            st.session_state.cross_df,
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
    st.dataframe(
        st.session_state.analysis_df,
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
                "State Change Date (Local)",
                timezone=str(get_localzone()),
                format="MM/DD/YYYY HH:mm:ss",
                width="medium"
            ),
            "SCD UTC": st.column_config.DatetimeColumn(
                "State Change Date (UTC)",
                format="MM/DD/YYYY HH:mm:ss",
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