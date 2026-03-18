"""
===========================================================
Prime Strength Gym - Payroll System
-----------------------------------------------------------
Author: Avinash Tanikella

FULL SYSTEM:
- Reads PT + Trainer Master
- Maps Trainer_Info (Key)
- Filters valid records
- Aggregates PT revenue
- Calculates:
    • Fixed Salary
    • Performance Pay
    • Commission
    • Final Salary
    • Performance %
    • Effective PT %
    • Feedback
===========================================================
"""

# ----------------------------------------------------------
# IMPORTS
# ----------------------------------------------------------

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ----------------------------------------------------------
# DATE INFO 
# ----------------------------------------------------------

today = datetime.today()
payroll_run_id = today.strftime("%b_%Y")   # Example: Mar_2026

# ----------------------------------------------------------
# APP TITLE
# ----------------------------------------------------------

st.title("🏋️ Prime Strength - Salary Calculator - ", today)


# ----------------------------------------------------------
# GOOGLE AUTH
# ----------------------------------------------------------

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
# SHEET CONFIG
# ----------------------------------------------------------

PT_SHEET_NAME = "PT Declaration form (Responses)"
PT_TAB_NAME = "Form Responses 1"

TRAINER_SHEET_NAME = "Trainers Master Sheet"
TRAINER_TAB_NAME = "Trainers"

# ----------------------------------------------------------
# CONNECT SHEETS
# ----------------------------------------------------------

try:
    pt_sheet = client.open(PT_SHEET_NAME).worksheet(PT_TAB_NAME)
    trainer_sheet = client.open(TRAINER_SHEET_NAME).worksheet(TRAINER_TAB_NAME)
except Exception as e:
    st.error(f"Sheet connection error: {e}")
    st.stop()

# ----------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------

pt_df = pd.DataFrame(pt_sheet.get_all_records())
trainer_df = pd.DataFrame(trainer_sheet.get_all_records())

st.subheader("📄 PT Data")
st.dataframe(pt_df.tail(20))

st.subheader("👤 Trainer Master")
st.dataframe(trainer_df.head(10))

# ----------------------------------------------------------
# BUTTON
# ----------------------------------------------------------

if st.button("🚀 Generate Payroll"):

    # ------------------------------------------------------
    # MERGE USING Trainer_Info
    # ------------------------------------------------------

    pt_with_emp = pd.merge(
        pt_df,
        trainer_df,
        on="Trainer_Info",
        how="left"
    )

    if pt_with_emp["Emp_ID"].isnull().any():
        st.error("Trainer_Info Key mismatch found!")
        st.stop()

    # ------------------------------------------------------
    # FILTER VALID RECORDS
    # ------------------------------------------------------

    filtered_df = pt_with_emp[
        (pt_with_emp["Payment_Verified_by_Manager"].astype(str).str.upper() == "YES") &
        (pt_with_emp["Payroll_Processed"].astype(str).str.upper() != "YES")
    ]

    if filtered_df.empty:
        st.warning("No valid records")
        st.stop()

    # ------------------------------------------------------
    # AGGREGATE PT REVENUE
    # ------------------------------------------------------

    revenue_df = filtered_df.groupby(
        ["Emp_ID", "Trainer_Name"]
    )["PT_Charges"].sum().reset_index()

    revenue_df.rename(columns={"PT_Charges": "PT_Revenue"}, inplace=True)

    # ------------------------------------------------------
    # MERGE BACK TO MASTER
    # ------------------------------------------------------

    merged_df = pd.merge(
        trainer_df,
        revenue_df,
        on=["Emp_ID", "Trainer_Name"],
        how="left"
    )

    merged_df["PT_Revenue"] = merged_df["PT_Revenue"].fillna(0)

    # ------------------------------------------------------
    # SALARY CALCULATION
    # ------------------------------------------------------

    def calculate_salary(row):

        revenue = row["PT_Revenue"]
        base = row["Base_Salary"]
        designation = row["Designation"]

        fixed = base * 0.60
        perf_component = base * 0.40

        # Performance Pay
        if revenue >= 80000:
            perf = perf_component
            perf_pct = 100
        elif revenue >= 50000:
            perf = perf_component * 0.75
            perf_pct = 75
        elif revenue >= 30000:
            perf = perf_component * 0.50
            perf_pct = 50
        else:
            perf = 0
            perf_pct = 0

        # Commission
        if designation == "Junior Trainer":
            commission = revenue * 0.30

        elif designation == "Senior Trainer":
            slabs = [(30000,0.30),(50000,0.35),(80000,0.40)]
            commission = progressive_calc(revenue, slabs)

        elif designation == "Lead Trainer":
            slabs = [(30000,0.40),(50000,0.45),(80000,0.50)]
            commission = progressive_calc(revenue, slabs)

        else:
            commission = 0

        final_salary = fixed + perf + commission

        effective_pct = (commission / revenue * 100) if revenue > 0 else 0

        return pd.Series({
            "Fixed_Salary": round(fixed,2),
            "Performance_Pay": round(perf,2),
            "Performance_%": perf_pct,
            "PT_Commission": round(commission,2),
            "Effective_PT_%": round(effective_pct,2),
            "Final_Salary": round(final_salary,2),
            "Feedback": feedback_msg(revenue)
        })

    # ------------------------------------------------------
    # PROGRESSIVE COMMISSION
    # ------------------------------------------------------

    def progressive_calc(revenue, slabs):

        commission = 0
        prev = 0

        for limit, rate in slabs:

            if revenue > limit:
                commission += (limit - prev) * rate
                prev = limit
            else:
                commission += (revenue - prev) * rate
                return commission

        commission += (revenue - prev) * slabs[-1][1]
        return commission

    # ------------------------------------------------------
    # FEEDBACK
    # ------------------------------------------------------

    def feedback_msg(revenue):

        if revenue == 0:
            return "No PT revenue generated"
        elif revenue < 30000:
            return "Below expectation"
        elif revenue < 50000:
            return "Good start"
        elif revenue < 80000:
            return "Great performance"
        else:
            return "Excellent performance"

    # ------------------------------------------------------
    # APPLY SALARY
    # ------------------------------------------------------

    salary_df = merged_df.apply(calculate_salary, axis=1)

    final_df = pd.concat([merged_df, salary_df], axis=1)

    final_df = final_df.sort_values(by="PT_Revenue", ascending=False)

    # ------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------

    st.success("✅ Payroll Generated Successfully")
    
    display_columns = [
        "Emp_ID",
        "Trainer_Name",
        "Phone_Number",
        "Email_Address",
        "Trainer_Type",
        "Designation",
        "Base_Salary",
        "PT_Revenue",
        "Fixed_Salary",
        "Performance_Pay",
        "Performance_%",
        "PT_Commission",
        "Effective_PT_%",
        "Final_Salary",
        "Feedback"]

    st.subheader("📊 Final Payroll Output")
    st.dataframe(final_df[display_columns])

    # Download option
    csv = final_df.to_csv(index=False).encode('utf-8')

    st.download_button(
        "📥 Download Payroll CSV",
        csv,
        "payroll.csv",
        "text/csv"
    )
