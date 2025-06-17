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
        'Inbox', 'Unresponsive', 'Completed', 'Unresponsive Talkscore', 'Passed MQ', 'Failed MQ',
        'TalkScore Retake', 'Unresponsive Talkscore Retake', 'Failed TalkScore', 'Cold Leads',
        'Cold Leads Talkscore', 'Cold Leads Talkscore Retake', 'On hold', 'Rejected',
        'Talent Pool', 'Shortlisted', 'Hired', 'Candidate Databank', 'For Talkscore',
        'Tier 2 Program', 'Tier 1 Program', 'For Versant', 'For Reengagement',
    ]

    # --- Filters Section ---
    st.header("Filters")
    
    # Filter 1: Date range for 'INVITATIONDT'
    min_date = tp['INVITATIONDT'].min().date()
    max_date = tp['INVITATIONDT'].max().date()
    
    # Calculate the default start date as 30 days ago from today
    default_start_date = datetime.now().date() - timedelta(days=30)

    # Ensure the default start date is not before the earliest date in the data
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
        select_all_sites = st.checkbox("Select All Sites", value=True)
        
        default_selection_sites = unique_sites if select_all_sites else []
        
        selected_sites = st.multiselect(
            "Campaign Site", 
            options=unique_sites, 
            default=default_selection_sites,
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
            select_all_titles = st.checkbox("Select All Titles", value=True)
            
            default_selection_titles = available_titles if select_all_titles else []

            selected_titles = st.multiselect(
                "Campaign Title", 
                options=available_titles, 
                default=default_selection_titles,
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
    ]
    
    # --- Download Button for Filtered Data ---
    st.download_button(
       label="Download Filtered Data as CSV",
       data=filtered_tp.to_csv(index=False).encode('utf-8'),
       file_name='filtered_talentpool_data.csv',
       mime='text/csv',
    )
    st.divider()

    # --- Data Analysis ---
    if not filtered_tp.empty:
        latest_activity = filtered_tp.loc[filtered_tp.groupby('CAMPAIGNINVITATIONID')['ACTIVITY_CREATED_AT'].idxmax()].copy()

        client_folder_activity_mask = (
            ~filtered_tp['FOLDER_FROM_TITLE'].isin(SYSTEM_FOLDERS) |
            ~filtered_tp['FOLDER_TO_TITLE'].isin(SYSTEM_FOLDERS)
        )
        ids_with_client_folder_history = filtered_tp.loc[client_folder_activity_mask, 'CAMPAIGNINVITATIONID'].unique()
        latest_activity['in_client_folder'] = latest_activity['CAMPAIGNINVITATIONID'].isin(ids_with_client_folder_history)

        new_endorsement = latest_activity[
            (latest_activity['FOLDER_TO_TITLE'] == 'Talent Pool') &
            (latest_activity['in_client_folder'] == False) &
            (latest_activity['FAILED_REASON'].isnull())
        ]

        rejected_waterfall = latest_activity[
            (latest_activity['in_client_folder'] == True) &
            (latest_activity['FOLDER_TO_TITLE'] != 'Candidate Databank') &
            (latest_activity['FAILED_REASON'].notnull())
        ]

        candidate_databank = latest_activity[
            latest_activity['FOLDER_TO_TITLE'] == 'Candidate Databank'
        ]

        def get_time_bucket(activity_date):
            now = datetime.now()
            delta = now - activity_date
            days = delta.days
            if days < 1: return "<24hrs"
            if 1 <= days <= 3: return "1-3 days"
            if 4 <= days <= 7: return "4-7 days"
            if 8 <= days <= 15: return "8-15 days"
            if 16 <= days <= 30: return "16-30 days"
            return "31+ days"

        if not new_endorsement.empty:
            new_endorsement.loc[:, 'time_bucket'] = new_endorsement['ACTIVITY_CREATED_AT'].apply(get_time_bucket)
        if not rejected_waterfall.empty:
            rejected_waterfall.loc[:, 'time_bucket'] = rejected_waterfall['ACTIVITY_CREATED_AT'].apply(get_time_bucket)
        if not candidate_databank.empty:
            candidate_databank.loc[:, 'time_bucket'] = candidate_databank['ACTIVITY_CREATED_AT'].apply(get_time_bucket)

        time_categories = ["<24hrs", "1-3 days", "4-7 days", "8-15 days", "16-30 days", "31+ days"]
        
        def create_pivot_series(df, name):
            if df.empty or 'time_bucket' not in df.columns:
                return pd.Series([0] * len(time_categories), index=time_categories, name=name)
            series = df.groupby('time_bucket')['CAMPAIGNINVITATIONID'].nunique().reindex(time_categories, fill_value=0)
            series.name = name
            return series

        pivot_new = create_pivot_series(new_endorsement, 'New (for endorsement)')
        pivot_rejected = create_pivot_series(rejected_waterfall, 'Rejected (for waterfall)')
        pivot_databank = create_pivot_series(candidate_databank, 'Candidate Databank (in Cooling Period)')

        pivot_table = pd.DataFrame([pivot_new, pivot_rejected, pivot_databank])

        pivot_table['Grand Total'] = pivot_table.sum(axis=1)
        pivot_table.loc['Grand Total'] = pivot_table.sum(axis=0)

        st.header("Talent Pool Breakdown")
        st.dataframe(pivot_table.style.format("{:.0f}"))

    else:
        st.warning("No data available for the selected filters.")

else:
    st.info("Data could not be loaded. Please check the file path and format.")
