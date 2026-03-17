"""
===========================================================
Prime Strength Gym - Payroll System
-----------------------------------------------------------
Author: Avinash Tanikella

PURPOSE:
This Streamlit app reads:
1. PT Declaration Sheet (trainer submissions)
2. Trainer Master Sheet (salary + designation)

Then:
- Filters valid PT entries
- Extracts EMP_ID from Trainer_Info
- Aggregates PT revenue per trainer
- Merges with Trainer Master
- Displays payroll-ready dataset

NOTE:
This is Phase 1 → Data Processing
Next Phase → Salary + Commission Calculation
===========================================================
"""

# ----------------------------------------------------------
# IMPORT LIBRARIES
# ----------------------------------------------------------

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials


# ----------------------------------------------------------
# APP TITLE
# ----------------------------------------------------------

st.title("🏋️ Prime Strength Gym - Payroll System")


# ----------------------------------------------------------
# GOOGLE SHEETS AUTHENTICATION
# ----------------------------------------------------------
"""
We use Streamlit secrets to securely store credentials.
credentials.json is NOT stored in GitHub.
"""

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

client = gspread.authorize(creds)


# ----------------------------------------------------------
# CONNECT TO GOOGLE SHEETS
# ----------------------------------------------------------
"""
IMPORTANT:
Replace below sheet names EXACTLY with your actual Google Sheet names
"""

PT_SHEET_NAME = "PT Declaration form (Responses)"         #PT Declarations spreadsheet
PT_TAB_NAME = "Form Responses 1"                          #PT Declaration Tab

TRAINER_SHEET_NAME = "Trainers Master Sheet"              #Trainers spreadsheet
TRAINER_TAB_NAME = "Trainers"                             #Trainers Tab

try:
    # Open PT Declaration Sheet
    pt_spreadsheet = client.open(PT_SHEET_NAME)                         #spreadsheet
    pt_sheet = pt_spreadsheet.worksheet(PT_TAB_NAME)                    #tab

    # Open Trainer Master Sheet
    trainer_spreadsheet = client.open(TRAINER_SHEET_NAME)               #spreadsheet
    trainer_sheet = trainer_spreadsheet.worksheet(TRAINER_TAB_NAME)     #tab

except Exception as e:
    st.error(f"Error connecting to Google Sheets: {e}")
    st.stop()


# ----------------------------------------------------------
# LOAD DATA INTO DATAFRAMES
# ----------------------------------------------------------

try:
    pt_data = pt_sheet.get_all_records()
    trainer_data = trainer_sheet.get_all_records()

    pt_df = pd.DataFrame(pt_data)
    trainer_df = pd.DataFrame(trainer_data)

except Exception as e:
    st.error(f"Error reading sheet data: {e}")
    st.stop()


# ----------------------------------------------------------
# SHOW DATA PREVIEW (FOR DEBUGGING PURPOSE)
# ----------------------------------------------------------

st.subheader("📄 PT Declaration Data (Preview)")
st.dataframe(pt_df.head())

st.subheader("👤 Trainer Master Data (Preview)")
st.dataframe(trainer_df.head())


# ----------------------------------------------------------
# MAIN ACTION BUTTON
# ----------------------------------------------------------

if st.button("🚀 Generate Payroll"):

    st.info("Processing payroll...")

    # ------------------------------------------------------
    # STEP 1: FILTER VALID RECORDS
    # ------------------------------------------------------
    """
    Conditions:
    - Payment verified by manager
    - Not already processed in payroll
    """

    filtered_df = pt_df[
        (pt_df["Payment_Verified_by_Manager"].astype(str).str.upper() == "YES") &
        (pt_df["Payroll_Processed"].astype(str).str.upper() != "YES")
    ]

    # Handle empty dataset
    if filtered_df.empty:
        st.warning("⚠️ No valid records found for payroll processing.")
        st.stop()

    # ------------------------------------------------------
    # STEP 2: EXTRACT TRAINER NAME & EMP_ID
    # ------------------------------------------------------
    """
    Trainer_Info format:
    "Trainer Name | EMP_ID"
    """

    try:
        split_cols = filtered_df['Trainer_Info'].str.split('|', expand=True)

        filtered_df['Trainer_Name'] = split_cols[0].str.strip()
        filtered_df['EMP_ID'] = split_cols[1].str.strip()

    except Exception as e:
        st.error(f"Error parsing Trainer_Info column: {e}")
        st.stop()

    # ------------------------------------------------------
    # STEP 3: AGGREGATE PT REVENUE
    # ------------------------------------------------------

    revenue_df = filtered_df.groupby(
        ['EMP_ID', 'Trainer_Name']
    )['PT_Charges'].sum().reset_index()

    revenue_df.rename(columns={"PT_Charges": "PT_Revenue"}, inplace=True)

    # ------------------------------------------------------
    # STEP 4: MERGE WITH TRAINER MASTER
    # ------------------------------------------------------

    merged_df = pd.merge(
        trainer_df,
        revenue_df,
        on="EMP_ID",
        how="left"
    )

    # Replace NaN with 0 for trainers without PT revenue
    merged_df["PT_Revenue"] = merged_df["PT_Revenue"].fillna(0)

    # ------------------------------------------------------
    # FINAL OUTPUT
    # ------------------------------------------------------

    st.success("✅ Payroll base data generated successfully!")

    st.subheader("📊 Payroll Output (Before Salary Calculation)")
    st.dataframe(merged_df)


# ----------------------------------------------------------
# END OF SCRIPT
# ----------------------------------------------------------
