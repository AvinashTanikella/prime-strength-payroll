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

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from datetime import datetime
import pytz

# ----------------------------------------------------------
# DATE INFO 
# ----------------------------------------------------------

ist = pytz.timezone('Asia/Kolkata')
today = datetime.now(ist)

# Previous month logic
if today.month == 1:
    prev_month = 12
    year = today.year - 1
else:
    prev_month = today.month - 1
    year = today.year

payroll_month = datetime(year, prev_month, 1).strftime("%b_%Y")   # For which Month Payroll is Processed  (Prev)
payroll_run_id = today.strftime("%b_%Y")                          # For which Month Payroll is Run(cur)
payroll_run_date = today.strftime("%d-%b-%Y")                     # The Date on which this Payroll was run

# ----------------------------------------------------------
# APP TITLE
# ----------------------------------------------------------

st.title("🏋️ Prime Strength - Salary Calculator")
st.markdown(f"### 📅 Payroll Month: {payroll_month}")
formatted_datetime = today.strftime("%d %b %Y | %I:%M %p")
st.markdown(f"### 📅 Run Time: {formatted_datetime}")


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

NFP_SHEET_NAME = "Trainers_NFP_Form"
NFP_TAB_NAME = "Trainers_NFP"
# ----------------------------------------------------------
# CONNECT SHEETS
# ----------------------------------------------------------

try:
    pt_sheet = client.open(PT_SHEET_NAME).worksheet(PT_TAB_NAME)
    trainer_sheet = client.open(TRAINER_SHEET_NAME).worksheet(TRAINER_TAB_NAME)
    nfp_sheet = client.open(NFP_SHEET_NAME).worksheet(NFP_TAB_NAME)
except Exception as e:
    st.error(f"Sheet connection error: {e}")
    st.stop()

# ----------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------

pt_df = pd.DataFrame(pt_sheet.get_all_records())
trainer_df = pd.DataFrame(trainer_sheet.get_all_records())
nfp_df = pd.DataFrame(nfp_sheet.get_all_records())

st.subheader("📄 PT Data")
st.dataframe(pt_df.tail(20))

st.subheader("👤 Trainer Master")
st.dataframe(trainer_df.head(10))

st.subheader("💰 Net Fixed Pay for the Trainers (as per HRMS)")
st.dataframe(nfp_df.head(10))

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
        nfp_df,
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
            return "Good going but try hard"
        elif revenue < 80000:
            return "Great performance"
        else:
            return "Excellent performance"

    # ------------------------------------------------------
    # APPLY SALARY
    # ------------------------------------------------------

    salary_df = merged_df.apply(calculate_salary, axis=1)

    final_df = pd.concat([merged_df, salary_df], axis=1)

    # Add tracking columns in required order
    final_df["Payroll_Month"] = payroll_month
    final_df["Payroll_Run_ID"] = payroll_run_id
    final_df["Payroll_Run_Date"] = payroll_run_date

    final_df = final_df.sort_values(by="PT_Revenue", ascending=False)

    # ------------------------------------------------------
    # UPDATE GOOGLE SHEET (MARK PROCESSED)
    # ------------------------------------------------------

    from gspread.utils import rowcol_to_a1
    
    records = pt_sheet.get_all_records()
    headers = pt_sheet.row_values(1)

    processed_col = headers.index("Payroll_Processed") + 1
    month_col = headers.index("Payroll_Month") + 1
    runid_col = headers.index("Payroll_Run_ID") + 1
    date_col = headers.index("Payroll_Run_Date") + 1

    updates = []

    for i, row in enumerate(records, start=2):

        verified = str(row.get("Payment_Verified_by_Manager", "")).upper()
        processed = str(row.get("Payroll_Processed", "")).upper()

        if verified == "YES" and processed != "YES":

            updates.append({
                "range": rowcol_to_a1(i, processed_col),
                "values": [["YES"]]
            })

            updates.append({
                "range": rowcol_to_a1(i, month_col),
                "values": [[payroll_month]]
            })

            updates.append({
                "range": rowcol_to_a1(i, runid_col),
                "values": [[payroll_run_id]]
            })

            updates.append({
                "range": rowcol_to_a1(i, date_col),
                "values": [[payroll_run_date]]
            })



    if updates:
        pt_sheet.batch_update(updates)

    # ------------------------------------------------------
    # pdf function
    # ------------------------------------------------------

    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import letter, landscape

    def generate_pdf(df, filename):

        doc = SimpleDocTemplate(
            filename,
            pagesize=landscape(letter)
        )

        styles = getSampleStyleSheet()
        elements = []

        # -------------------------------
        # HEADER (LEFT ALIGNED)
        # -------------------------------

        elements.append(Paragraph("Prime Strength Gym - Payroll Report", styles['Title']))
        
        elements.append(Paragraph(f"Payroll Month: {payroll_month}", styles['Normal']))
        elements.append(Paragraph(f"Payroll Run ID: {payroll_run_id}", styles['Normal']))
        elements.append(Paragraph(f"Run Date: {payroll_run_date}", styles['Normal']))

        # Space before table
        elements.append(Spacer(1, 12))   # 1 line space

        # -------------------------------
        # TABLE
        # -------------------------------

        table_data = [df.columns.tolist()] + df.values.tolist()

        table = Table(table_data, repeatRows=1)

        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('ALIGN', (0,0), (-1,-1), 'CENTER')
        ]))

        elements.append(table)

        # -------------------------------
        # FOOTER
        # -------------------------------

        elements.append(Spacer(1, 20))  # space after table
        elements.append(Spacer(1, 20))  # 2 lines gap

        elements.append(Paragraph(
            "For Prime Strength internal use only",
            styles['Italic']
        ))

        doc.build(elements)

    # ------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------

    st.success(f"✅ Payroll Generated Successfully | Run: {payroll_run_id} | Time: {today.strftime('%d %b %Y, %I:%M %p')}")
    
    display_columns = [
        "Payroll_Month",       
        "Payroll_Run_ID",      
        "Payroll_Run_Date",    
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

    pdf_columns = [
        "Emp_ID",
        "Trainer_Name",
        "Designation",
        "PT_Revenue",
        "Fixed_Salary",
        "Performance_Pay",
        "Performance_%",
        "PT_Commission",
        "Effective_PT_%",
        "Final_Salary",
        "Feedback"]
    
    pdf_file = "payroll.pdf"
    generate_pdf(final_df[pdf_columns], pdf_file)

    with open(pdf_file, "rb") as f:
        st.download_button(
            "📄 Download Payroll PDF",
            f,
            file_name="payroll.pdf"
    )
