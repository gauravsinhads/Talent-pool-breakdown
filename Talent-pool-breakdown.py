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
        'Tier 2 Program', 'Tier 1 Program', 'For Versant', 'For Reengagement'
    ]

    # --- Filters Expander ---
    with st.expander("Filter Options"):
        # Filter 1: Date range for 'INVITATIONDT'
        min_date = tp['INVITATIONDT'].min().date()
        max_date = tp['INVITATIONDT'].max().date()
        start_date, end_date = st.date_input(
            "Invitation Date Range",
            [min_date, max_date],
            min_value=min_date,
            max_value=max_date
        )

        # Filter 2: Multiselect dropdown for 'CAMPAIGN_SITE'
        all_sites = tp['CAMPAIGN_SITE'].dropna().unique()
        selected_sites = st.multiselect(
            "Campaign Site",
            all_sites,
            default=all_sites
        )

        # Filter 3: Dependent multiselect for 'CAMPAIGNTITLE'
        # Options for campaign titles are dependent on the selected campaign sites
        if selected_sites:
            available_titles = tp[tp['CAMPAIGN_SITE'].isin(selected_sites)]['CAMPAIGNTITLE'].dropna().unique()
        else:
            available_titles = tp['CAMPAIGNTITLE'].dropna().unique()

        selected_titles = st.multiselect(
            "Campaign Title",
            available_titles,
            default=available_titles
        )


    # --- Data Filtering Logic ---
    # Apply filters to the dataframe
    # Convert start_date and end_date to datetime for comparison
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    filtered_tp = tp[
        (tp['INVITATIONDT'] >= start_datetime) &
        (tp['INVITATIONDT'] <= end_datetime) &
        (tp['CAMPAIGN_SITE'].isin(selected_sites)) &
        (tp['CAMPAIGNTITLE'].isin(selected_titles))
    ]

    # --- Data Analysis ---
    if not filtered_tp.empty:
        # Get the latest activity for each campaign invitation
        latest_activity = filtered_tp.loc[filtered_tp.groupby('CAMPAIGNINVITATIONID')['ACTIVITY_CREATED_AT'].idxmax()].copy()

        # --- Optimized check for client folder history ---
        # This vectorized approach is much faster than applying a function row-by-row.
        # 1. Identify all activities involving a client folder (i.e., not in SYSTEM_FOLDERS).
        client_folder_activity_mask = (
            ~filtered_tp['FOLDER_FROM_TITLE'].isin(SYSTEM_FOLDERS) |
            ~filtered_tp['FOLDER_TO_TITLE'].isin(SYSTEM_FOLDERS)
        )
        # 2. Get the unique IDs of candidates who have had at least one such activity.
        ids_with_client_folder_history = filtered_tp.loc[client_folder_activity_mask, 'CAMPAIGNINVITATIONID'].unique()

        # 3. Create the 'in_client_folder' column by checking if an ID is in our list.
        latest_activity['in_client_folder'] = latest_activity['CAMPAIGNINVITATIONID'].isin(ids_with_client_folder_history)


        # --- Categorize Candidates ---
        # 1. New (for endorsement)
        new_endorsement = latest_activity[
            (latest_activity['FOLDER_TO_TITLE'] == 'Talent Pool') &
            (latest_activity['in_client_folder'] == False) &
            (latest_activity['FOLDER_TO_TITLE'] != 'Candidate Databank') &
            (latest_activity['FAILED_REASON'].isnull())
        ]

        # 2. Rejected (for waterfall)
        rejected_waterfall = latest_activity[
            (latest_activity['in_client_folder'] == True) &
            (latest_activity['FOLDER_TO_TITLE'] != 'Candidate Databank') &
            (latest_activity['FAILED_REASON'].notnull())
        ]

        # 3. Candidate Databank (in Cooling Period)
        candidate_databank = latest_activity[
            latest_activity['FOLDER_TO_TITLE'] == 'Candidate Databank'
        ]

        # --- Time Bucketing ---
        def get_time_bucket(activity_date):
            """Categorizes a date into predefined time buckets based on days from now."""
            now = datetime.now()
            delta = now - activity_date
            days = delta.days

            if days < 1:
                return "<24hrs"
            elif 1 <= days <= 3:
                return "1-3 days"
            elif 4 <= days <= 7:
                return "4-7 days"
            elif 8 <= days <= 15:
                return "8-15 days"
            elif 16 <= days <= 30:
                return "16-30 days"
            else: # days >= 31
                return "31+ days"

        # Apply time bucketing
        new_endorsement['time_bucket'] = new_endorsement['ACTIVITY_CREATED_AT'].apply(get_time_bucket)
        rejected_waterfall['time_bucket'] = rejected_waterfall['ACTIVITY_CREATED_AT'].apply(get_time_bucket)
        candidate_databank['time_bucket'] = candidate_databank['ACTIVITY_CREATED_AT'].apply(get_time_bucket)

        # --- Create Pivot Table ---
        time_categories = ["<24hrs", "1-3 days", "4-7 days", "8-15 days", "16-30 days", "31+ days"]
        
        # Function to create a pivot series for a given dataframe
        def create_pivot_series(df, name):
            series = df.groupby('time_bucket')['CAMPAIGNINVITATIONID'].nunique().reindex(time_categories, fill_value=0)
            series.name = name
            return series

        # Create series for each category
        pivot_new = create_pivot_series(new_endorsement, 'New (for endorsement)')
        pivot_rejected = create_pivot_series(rejected_waterfall, 'Rejected (for waterfall)')
        pivot_databank = create_pivot_series(candidate_databank, 'Candidate Databank (in Cooling Period)')

        # Combine into a final DataFrame
        pivot_table = pd.DataFrame([pivot_new, pivot_rejected, pivot_databank])

        # Add Grand Totals
        pivot_table['Grand Total'] = pivot_table.sum(axis=1)
        pivot_table.loc['Grand Total'] = pivot_table.sum(axis=0)

        # Display the pivot table
        st.header("Talent Pool Breakdown")
        st.dataframe(pivot_table.style.format("{:.0f}")) # Format to show integers

    else:
        st.warning("No data available for the selected filters.")

else:
    st.info("Data could not be loaded. Please check the file path and format.")
