import pandas as pd
from io import BytesIO
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

def _df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "data") -> bytes:
    """Return an XLSX file (bytes) containing df."""
    bio = BytesIO()
    # Prefer xlsxwriter if available, else fall back to openpyxl
    try:
        engine = "xlsxwriter"
        with pd.ExcelWriter(bio, engine=engine) as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    except Exception:
        engine = "openpyxl"
        with pd.ExcelWriter(bio, engine=engine) as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    bio.seek(0)
    return bio.read()

def _df_to_html_table(df: pd.DataFrame, title: str = None) -> str:
    """Simple HTML table with light styling for email."""
    if df is None or df.empty:
        return f"<h3>{title or ''}</h3><p><i>No rows.</i></p>"
    html_tbl = df.to_html(index=False, border=0, justify="left", classes="report-table")
    style = """
    <style>
      .report-table {border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px;}
      .report-table th, .report-table td {border: 1px solid #ddd; padding: 6px 8px;}
      .report-table th {background: #f2f2f2; font-weight: 600;}
      .report-table tr:nth-child(even) {background: #fafafa;}
    </style>
    """
    header = f"<h3>{title}</h3>" if title else ""
    return style + header + html_tbl

def send_email_report(
    recipients,
    subject,
    overall_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    failed_df: pd.DataFrame,
    sender="saisrikar.ravipati@cvshealth.com",
    smtp_host="smtppaz.corp.cvscaremark.com",
    smtp_port=25,
    use_starttls=True
):
    # --- Build HTML body (Overall Summary inline) ---
    overall_html = _df_to_html_table(overall_df, title="Overall Summary")
    html_body = f"""
    <html>
      <body>
        <p>Hello Team,</p>
        <p>Below is the Overall Summary for this run:</p>
        {overall_html}
        <p>Attached: Summary All DF and Failed DFS DF as Excel files.</p>
        <p>Thanks!</p>
      </body>
    </html>
    """

    # --- Build attachments as Excel ---
    attachments = []
    if summary_df is not None:
        attachments.append((
            "summary_all_df.xlsx",
            _df_to_excel_bytes(summary_df, sheet_name="summary_all")
        ))
    if failed_df is not None:
        attachments.append((
            "failed_dfs_df.xlsx",
            _df_to_excel_bytes(failed_df, sheet_name="failed_dfs")
        ))

    # --- Create email ---
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(html_body, "html"))

    for fname, fbytes in attachments:
        part = MIMEApplication(fbytes, Name=fname)
        part["Content-Disposition"] = f'attachment; filename="{fname}"'
        msg.attach(part)

    # --- Send ---
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_starttls:
                try:
                    server.starttls()
                except Exception:
                    pass  # best-effort only
            server.sendmail(sender, recipients, msg.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

# ----------------------------
# USAGE (edit recipients/subject as you already do)
# ----------------------------
send_email_report(
    recipients=[
        "saisrikar.ravipati@cvshealth.com",
        "Surendra.Koththigoda@CVSHealth.com",
        "RadheShyam.Ramesh@CVSHealth.com",
        "Aaron.Linnear@CVSHealth.com",
        "Mounica.Ponnam@CVSHealth.com",
        "Abhinanditha.Ippagunta@CVSHealth.com",
        "KamalkumarRajeshbhai.Patel@CVSHealth.com",
    ],
    subject=f"QAAP Daily Regression | Integrated Tests - {cluster_name}",
    overall_df=overall_summary_all_df,
    summary_df=summary_all_df,
    failed_df=fail_dfs_df
)

