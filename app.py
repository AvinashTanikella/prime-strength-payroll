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
    • Raring-Message
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

PT_SHEET_NAME = "PT_Data"
PT_TAB_NAME = "PT_Declarations-ALL"

TRAINER_SHEET_NAME = "Trainers_Master_Data"
TRAINER_TAB_NAME = "Trainers_Details"

NFP_SHEET_NAME = "Trainers_NFP_Data"
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

st.subheader("👤 Trainer's Master Data - Company Defined")
st.dataframe(trainer_df[["Emp_ID","Trainer_Name","Phone_Number","Trainer_Type","Designation","Base_Salary","Fixed_Pay(60% of Base)","Performance_Pay(40% of Base)","WP_Resp_Allowance","Status"]].head(10))

st.subheader("💰 Trainer's - NFP Data (HR Defined - as per HRMS)")
st.dataframe(nfp_df[["Trainer_Info", "Month_Year", "Net_Fixed_Pay"]].head(10))

st.subheader("📄 PT Declarations - Trainers Defined")
st.dataframe(pt_df[["Trainer_Info","Client Name","PT_Charges","Payment_Verified_by_Manager"]].tail(60))

# ----------------------------------------------------------
# NORMALIZE MONTH FORMAT (NEW)
# ----------------------------------------------------------
# This ensures Month_Year is always in format: Feb_2026
# Handles cases like: Feb-2026, February 2026, etc.

def normalize_month(val):
    try:
        val = str(val).replace("_", "-").upper()
        return pd.to_datetime(val, errors='coerce').strftime("%b_%Y")
    except:
        return None

nfp_df["Month_Year"] = nfp_df["Month_Year"].apply(normalize_month)

# ----------------------------------------------------------
# BUTTON
# ----------------------------------------------------------

if st.button("🚀 Generate Payroll"):

    # ------------------------------------------------------
    # STEP 1: START WITH TRAINER MASTER (DRIVER)
    # ------------------------------------------------------

    merged_df = trainer_df.copy()

    # ------------------------------------------------------
    # STEP 2: FILTER FIXED PAY FOR REQUIRED MONTH
    # ------------------------------------------------------

    nfp_filtered = nfp_df[
        nfp_df["Month_Year"].str.upper() == payroll_month.upper()
    ]

    if nfp_filtered.empty:
        st.error(f"No Fixed Pay data found for {payroll_month}")
        st.stop()

    if nfp_filtered["Trainer_Info"].duplicated().any():
        st.error("Duplicate Fixed Pay entries found for same trainer")
        st.stop()

    # ------------------------------------------------------
    # STEP 3: MERGE NFP (MANDATORY)
    # ------------------------------------------------------

    merged_df = pd.merge(
        merged_df,
        nfp_filtered[["Trainer_Info", "Net_Fixed_Pay"]],
        on="Trainer_Info",
        how="left"
    )

    if merged_df["Net_Fixed_Pay"].isnull().any():
        st.error("Missing Fixed Pay for some trainers")
        st.stop()

    # ------------------------------------------------------
    # STEP 4: PROCESS PT DATA (OPTIONAL)
    # ------------------------------------------------------

    pt_with_emp = pd.merge(
        pt_df,
        trainer_df,
        on="Trainer_Info",
        how="left"
    )

    if pt_with_emp["Emp_ID"].isnull().any():
        st.error("Trainer_Info Key mismatch found in PT data!")
        st.stop()

    filtered_df = pt_with_emp[
        (pt_with_emp["Payment_Verified_by_Manager"].astype(str).str.upper() == "YES") &
        (pt_with_emp["Payroll_Processed"].astype(str).str.upper() != "YES")
    ]

    if not filtered_df.empty:
        revenue_df = filtered_df.groupby(
            ["Emp_ID", "Trainer_Name"]
        )["PT_Charges"].sum().reset_index()

        revenue_df.rename(columns={"PT_Charges": "PT_Revenue"}, inplace=True)
    else:
        st.warning("No PT records found. Continuing with zero revenue.")
        revenue_df = pd.DataFrame(columns=["Emp_ID", "Trainer_Name", "PT_Revenue"])

    # ------------------------------------------------------
    # STEP 5: MERGE PT DATA (LAST)
    # ------------------------------------------------------

    merged_df = pd.merge(
        merged_df,
        revenue_df,
        on=["Emp_ID", "Trainer_Name"],
        how="left"
    )

    # CRITICAL FIX
    merged_df["PT_Revenue"] = merged_df.get("PT_Revenue", 0).fillna(0)

    # Ensure allowance safe
    merged_df["WP_Resp_Allowance"] = merged_df["WP_Resp_Allowance"].fillna(0)


    # ------------------------------------------------------
    # PROGRESSIVE COMMISSION (FIXED POSITION)
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
    # FEEDBACK FUNCTION
    # ------------------------------------------------------

    def rating_msg(revenue):

        if revenue == 0:
            return "1-Poor"
        elif revenue < 30000:
            return "2-Below Expctd."
        elif revenue < 50000:
            return "3-Average"
        elif revenue < 80000:
            return "4-Great"
        else:
            return "5-Excellent"
    
    # ------------------------------------------------------
    # SALARY CALCULATION
    # ------------------------------------------------------

    def calculate_salary(row):

        revenue = float(row.get("PT_Revenue", 0))
        base = float(row.get("Base_Salary", 0))
        designation = row.get("Designation", "")
        wp_allowance = float(row.get("WP_Resp_Allowance", 0))
        net_fixed = float(row.get("Net_Fixed_Pay", 0))

        fixed = base * 0.60
        perf_component = base * 0.40

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

        penalty = net_fixed * 0.50 if revenue == 0 else 0

        final_salary = net_fixed + perf + commission + wp_allowance - penalty
        effective_pct = (commission / revenue * 100) if revenue > 0 else 0

        return pd.Series({
        # ---------------- IDEAL ----------------
        "Ideal_Base_Salary": round(base, 2),
        "Ideal_Fixed_Pay": round(fixed, 2),
        "Ideal_Performance_Pay": round(perf_component, 2),

        # ---------------- ACTUAL ----------------
        "Net_Fixed_Pay": round(net_fixed, 2),
        "Net_Performance_Pay": round(perf, 2),

        # ---------------- PERFORMANCE ----------------
        "PT_Revenue": round(revenue, 2),
        "PT_Commission": round(commission, 2),
        "Effective_PT_%": round(effective_pct, 2),

        # ---------------- ADJUSTMENTS ----------------
        "WP_Allowance": round(wp_allowance, 2),
        "Penalty": round(penalty, 2),

        # ---------------- FINAL ----------------
        "Final_Salary": round(final_salary, 2),
        "Performance_%": perf_pct,
        "Rating-Msg": rating_msg(revenue)
    })

    # ------------------------------------------------------
    # APPLY SALARY
    # ------------------------------------------------------

    salary_df = merged_df.apply(calculate_salary, axis=1)

    # Clean overwrite (no duplicates)
    for col in salary_df.columns:
        merged_df[col] = salary_df[col]

    final_df = merged_df.copy()

    # ------------------------------------------------------
    # TRACKING FIELDS
    # ------------------------------------------------------

    final_df["Payroll_Month"] = payroll_month
    final_df["Payroll_Run_ID"] = payroll_run_id
    final_df["Payroll_Run_Date"] = payroll_run_date

    final_df = final_df.sort_values(by="PT_Revenue", ascending=False)

    # ------------------------------------------------------
    # TOTAL ROW
    # ------------------------------------------------------

    total_row = {
        "Emp_ID": "TOTALS",
        "Trainer_Name": "",
        "Designation": "",
        "PT_Revenue": final_df["PT_Revenue"].sum(),
        "Net_Fixed_Pay": final_df["Net_Fixed_Pay"].sum(),
        "Net_Performance_Pay": final_df["Net_Performance_Pay"].sum(),
        "PT_Commission": final_df["PT_Commission"].sum(),
        "WP_Allowance": final_df["WP_Allowance"].sum(),
        "Penalty": final_df["Penalty"].sum(),
        "Final_Salary": final_df["Final_Salary"].sum(),
        "Performance_%": "-",
        "Effective_PT_%": "-",
        "Rating-Msg": "-"
    }

    total_df = pd.DataFrame([total_row])
    export_df = pd.concat([final_df, total_df], ignore_index=True)
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
    from reportlab.lib.pagesizes import A4, landscape

    def generate_pdf(df, filename):

        doc = SimpleDocTemplate(
            filename,
            pagesize=landscape(A4),
            leftMargin=10,
            rightMargin=10,
            topMargin=10,
            bottomMargin=10
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

        available_width = doc.width
        num_cols = len(df.columns)

        table = Table(table_data, repeatRows=1, colWidths=[available_width / num_cols] * num_cols)

        table.setStyle(TableStyle([
        # -------------------------------
        # EXISTING STYLING
        # -------------------------------
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('FONTSIZE', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        # -------------------------------        
        # PADDING
        # -------------------------------
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        # -------------------------------
        # TOTAL ROW STYLING
        # -------------------------------
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        #   ('FONTSIZE', (0, -1), (-1, -1), 8),
        #   ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
        # -------------------------------
        # MERGE FIRST 3 COLUMNS
        # -------------------------------
            ('SPAN', (0, -1), (2, -1)),   # Merge col 0 to 2
        # Align TOTALS text to left
            ('ALIGN', (0, -1), (2, -1), 'LEFT'),

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
    # ---------------- TRACKING ----------------
    "Payroll_Month",
    "Payroll_Run_ID",
    "Payroll_Run_Date",

    # ---------------- EMPLOYEE ----------------
    "Emp_ID",
    "Trainer_Name",
    "Phone_Number",
    "Email_Address",
    "Trainer_Type",
    "Designation",

    # ---------------- IDEAL ----------------
    "Ideal_Base_Salary",
    "Ideal_Fixed_Pay",
    "Ideal_Performance_Pay",

    # ---------------- ACTUAL ----------------
    "Net_Fixed_Pay",
    "Net_Performance_Pay",
    "Performance_%",

    # ---------------- PERFORMANCE ----------------
    "PT_Revenue",
    "PT_Commission",
    "Effective_PT_%",

    # ---------------- ADJUSTMENTS ----------------
    "WP_Allowance",
    "Penalty",

    # ---------------- FINAL ----------------
    "Final_Salary",
    "Rating-Msg"
    ]

    st.subheader("📊 Final Payroll Output")
    st.dataframe(final_df[display_columns])

    # Download option
    csv = export_df[display_columns].to_csv(index=False).encode('utf-8')

    csv_filename = f"PrimeStrength_Payroll_{payroll_month}.csv"
    
    st.download_button(
        "📥 Download Payroll CSV",
        csv,
        csv_filename,
        "text/csv"
    )

    pdf_columns = [
        "Emp_ID",
        "Trainer_Name",
        "Designation",
        "Net_Fixed_Pay",
        "Net_Performance_Pay",
        "Performance_%",
        "PT_Revenue",
        "PT_Commission",
        "Effective_PT_%",
        "WP_Allowance",
        "Penalty",
        "Final_Salary",
        "Rating-Msg"]
    
    pdf_file = f"PrimeStrength_Payroll_{payroll_month}.pdf"

    pdf_export_df = pd.concat(
    [final_df[pdf_columns], total_df[pdf_columns]],
    ignore_index=True)

    pdf_export_df = pdf_export_df.fillna("").astype(str)

    generate_pdf(pdf_export_df, pdf_file)

    with open(pdf_file, "rb") as f:
        st.download_button(
            "📄 Download Payroll PDF",
            f,
            file_name=pdf_file
    )
