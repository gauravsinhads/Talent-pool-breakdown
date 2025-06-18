import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Set the page title for the Streamlit application
st.set_page_config(page_title='TALENTPOOL BREAKDOWN', layout="wide")
st.title('TALENTPOOL BREAKDOWN')

# --- Data Loading and Preprocessing ---
@st.cache_data
def load_data():
    """
    Loads and preprocesses the data from the CSV file.
    - Reads the CSV into a pandas DataFrame.
    - Converts date/time columns to datetime objects.
    - Handles potential errors during data loading.
    """
    try:
        # Load the dataset
        tp = pd.read_csv("SOURCING & EARLY STAGE METRICS.csv")

        # Convert date columns to datetime objects, coercing errors to NaT (Not a Time)
        tp['INVITATIONDT'] = pd.to_datetime(tp['INVITATIONDT'], errors='coerce')
        tp['ACTIVITY_CREATED_AT'] = pd.to_datetime(tp['ACTIVITY_CREATED_AT'], errors='coerce')

        # Drop rows where essential date columns have NaT values after conversion
        tp.dropna(subset=['INVITATIONDT', 'ACTIVITY_CREATED_AT'], inplace=True)

        return tp
    except FileNotFoundError:
        st.error("The data file 'SOURCING & EARLY STAGE METRICS.csv' was not found.")
        st.info("Please make sure the CSV file is in the same directory as the Streamlit script.")
        return None

# Load the data using the cached function
tp = load_data()

# Proceed only if data is loaded successfully
if tp is not None:

    # --- System Folder Definition ---
    SYSTEM_FOLDERS = [
        '', 'Inbox', 'Unresponsive', 'Completed', 'Unresponsive Talkscore', 'Passed MQ', 'Failed MQ',
        'TalkScore Retake', 'Unresponsive Talkscore Retake', 'Failed TalkScore', 'Cold Leads',
        'Cold Leads Talkscore', 'Cold Leads Talkscore Retake', 'On hold', 'Rejected',
        'Talent Pool', 'Shortlisted', 'Hired', 'Candidate Databank', 'For Talkscore',
        'Tier 2 Program', 'Tier 1 Program', 'For Versant', 'For Reengagement'
    ]

    # --- Filters Section ---
    st.header("Filters")
    
    # Filter 1: Date range for 'INVITATIONDT'
    min_date = tp['INVITATIONDT'].min().date()
    max_date = tp['INVITATIONDT'].max().date()
    
    default_start_date = datetime.now().date() - timedelta(days=30)
    if default_start_date < min_date:
        default_start_date = min_date

    start_date, end_date = st.date_input(
        "Invitation Date Range",
        [default_start_date, max_date],
        min_value=min_date,
        max_value=max_date
    )
    st.divider()

    # Filter 2: Expander for 'CAMPAIGN_SITE' with Select All
    with st.expander("Select Campaign Site(s)"):
        unique_sites = sorted(tp['CAMPAIGN_SITE'].dropna().unique())
        select_all_sites = st.checkbox("Select All Sites", value=True, key='sites_select_all')
        default_selection_sites = unique_sites if select_all_sites else []
        selected_sites = st.multiselect(
            "Campaign Site", options=unique_sites, default=default_selection_sites,
            label_visibility="collapsed"
        )
    st.divider()

    # Filter 3: Dependent Expander for 'CAMPAIGNTITLE' with Select All
    with st.expander("Select Campaign Title(s)"):
        if not selected_sites:
            st.warning("Please select a Campaign Site to see available titles.")
            selected_titles = []
        else:
            available_titles = sorted(tp[tp['CAMPAIGN_SITE'].isin(selected_sites)]['CAMPAIGNTITLE'].dropna().unique())
            select_all_titles = st.checkbox("Select All Titles", value=True, key='titles_select_all')
            default_selection_titles = available_titles if select_all_titles else []
            selected_titles = st.multiselect(
                "Campaign Title", options=available_titles, default=default_selection_titles,
                label_visibility="collapsed"
            )
    st.divider()

    # --- Data Filtering Logic ---
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    filtered_tp = tp[
        (tp['INVITATIONDT'] >= start_datetime) &
        (tp['INVITATIONDT'] <= end_datetime) &
        (tp['CAMPAIGN_SITE'].isin(selected_sites)) &
        (tp['CAMPAIGNTITLE'].isin(selected_titles))
    ].copy()

    # --- Data Analysis and Labeling ---
    if not filtered_tp.empty:
        latest_activity = filtered_tp.loc[filtered_tp.groupby('CAMPAIGNINVITATIONID')['ACTIVITY_CREATED_AT'].idxmax()].copy()

        # A folder is a 'Client Folder' if it's not null/NaN and not in the SYSTEM_FOLDERS list.
        from_is_client = (filtered_tp['FOLDER_FROM_TITLE'].notna()) & (~filtered_tp['FOLDER_FROM_TITLE'].isin(SYSTEM_FOLDERS))
        to_is_client = (filtered_tp['FOLDER_TO_TITLE'].notna()) & (~filtered_tp['FOLDER_TO_TITLE'].isin(SYSTEM_FOLDERS))
        client_folder_activity_mask = from_is_client | to_is_client

        ids_with_client_folder_history = filtered_tp.loc[client_folder_activity_mask, 'CAMPAIGNINVITATIONID'].unique()
        latest_activity['in_client_folder'] = latest_activity['CAMPAIGNINVITATIONID'].isin(ids_with_client_folder_history)

        # Define categorization functions
        def get_row_label(row):
            if row['FOLDER_TO_TITLE'] == 'Candidate Databank':
                return 'Candidate Databank (in Cooling Period)'
            elif (row['FOLDER_TO_TITLE'] == 'Talent Pool' and not row['in_client_folder'] and pd.isnull(row['FAILED_REASON'])):
                return 'New (for endorsement)'
            elif (row['in_client_folder'] and row['FOLDER_TO_TITLE'] != 'Candidate Databank' and pd.notnull(row['FAILED_REASON'])):
                return 'Rejected (for waterfall)'
            return None # Return None if no category matches

        def get_time_bucket(activity_date):
            if pd.isnull(activity_date): return None
            days = (datetime.now() - activity_date).days
            if days < 1: return "<24hrs"
            if 1 <= days <= 3: return "1-3 days"
            if 4 <= days <= 7: return "4-7 days"
            if 8 <= days <= 15: return "8-15 days"
            if 16 <= days <= 30: return "16-30 days"
            return "31+ days"

        # Apply labels to the latest activities
        latest_activity['Row_label'] = latest_activity.apply(get_row_label, axis=1)
        latest_activity['Column_label'] = latest_activity['ACTIVITY_CREATED_AT'].apply(get_time_bucket)

        # Prepare data for download by merging labels into the filtered raw data
        label_mapping = latest_activity[['CAMPAIGNINVITATIONID', 'Row_label', 'Column_label']]
        data_for_download = pd.merge(
            filtered_tp, label_mapping, on='CAMPAIGNINVITATIONID', how='left'
        )
        
        # --- Download Button for Labeled Data ---
        st.download_button(
           label="Download Filtered Data as CSV (with labels)",
           data=data_for_download.to_csv(index=False).encode('utf-8'),
           file_name='filtered_talentpool_data_with_labels.csv',
           mime='text/csv',
        )
        st.divider()

        # --- Pivot Table Calculation (Time Buckets) ---
        pivot_data = latest_activity.dropna(subset=['Row_label'])
        
        if not pivot_data.empty:
            st.header("TALENTPOOL BREAKDOWN")
            pivot_table_time = pd.crosstab(
                index=pivot_data['Row_label'],
                columns=pivot_data['Column_label'],
                values=pivot_data['CAMPAIGNINVITATIONID'],
                aggfunc='nunique'
            ).fillna(0)

            time_categories = ["<24hrs", "1-3 days", "4-7 days", "8-15 days", "16-30 days", "31+ days"]
            row_categories = ['New (for endorsement)', 'Rejected (for waterfall)', 'Candidate Databank (in Cooling Period)']
            pivot_table_time = pivot_table_time.reindex(index=row_categories, columns=time_categories, fill_value=0)

            pivot_table_time['Grand Total'] = pivot_table_time.sum(axis=1)
            pivot_table_time.loc['Grand Total'] = pivot_table_time.sum(axis=0)
            
            st.dataframe(pivot_table_time.style.format("{:.0f}"))
            st.divider()

            # --- Pivot Table Calculation (Daily) ---
            st.header("TALENTPOOL BREAKDOWN (Daily)")
            
            # Filter for the last 7 days, excluding today
            today = datetime.now().date()
            seven_days_ago = today - timedelta(days=7)
            daily_pivot_data = pivot_data[
                (pivot_data['ACTIVITY_CREATED_AT'].dt.date >= seven_days_ago) &
                (pivot_data['ACTIVITY_CREATED_AT'].dt.date < today)
            ].copy()
            
            if not daily_pivot_data.empty:
                daily_pivot_data['activity_date_str'] = daily_pivot_data['ACTIVITY_CREATED_AT'].dt.strftime('%b_%d')
                
                daily_pivot_table = pd.crosstab(
                    index=daily_pivot_data['Row_label'],
                    columns=daily_pivot_data['activity_date_str'],
                    values=daily_pivot_data['CAMPAIGNINVITATIONID'],
                    aggfunc='nunique'
                ).fillna(0)

                # Define columns for the last 7 days to ensure they are all present and sorted, excluding today
                daily_cols = [(today - timedelta(days=i)).strftime('%b_%d') for i in range(7, 0, -1)]
                daily_pivot_table = daily_pivot_table.reindex(index=row_categories, columns=daily_cols, fill_value=0)

                # Add Grand Totals
                daily_pivot_table['Grand Total'] = daily_pivot_table.sum(axis=1)
                daily_pivot_table.loc['Grand Total'] = daily_pivot_table.sum(axis=0)

                st.dataframe(daily_pivot_table.style.format("{:.0f}"))
            else:
                st.warning("No activity recorded in the last 7 days for the selected filters.")

        else:
            st.warning("No candidates matched the breakdown criteria for the selected filters.")

    else:
        st.warning("No data available for the selected filters.")
else:
    st.info("Data could not be loaded. Please check the file path 
