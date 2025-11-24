import pandas as pd
from io import BytesIO
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

def _df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "data") -> bytes:
    bio = BytesIO()
    try:
        with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    except Exception:
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    bio.seek(0)
    return bio.read()

def _overall_summary_to_html(df: pd.DataFrame, title: str = "Overall Summary") -> str:
    """
    Renders Overall Summary with conditional coloring:
      - Passed column green
      - Failed column red
      - If Failed > 0, highlight row lightly in red tint
    Works even if column names are slightly different (case/space tolerant).
    """
    if df is None or df.empty:
        return f"<h3>{title}</h3><p><i>No rows.</i></p>"

    # Normalize column lookup
    cols_norm = {c: c.strip().lower() for c in df.columns}
    passed_col = next((c for c,n in cols_norm.items() if n in ("passed", "pass", "passed_cnt")), None)
    failed_col = next((c for c,n in cols_norm.items() if n in ("failed", "fail", "failed_cnt")), None)

    def fmt_cell(value, col_name):
        if col_name == passed_col:
            return f'<span style="color:#1a7f37;font-weight:700;">{value}</span>'  # green
        if col_name == failed_col:
            return f'<span style="color:#d1242f;font-weight:700;">{value}</span>'  # red
        return str(value)

    # Build rows manually so we can style per cell/row
    header_cells = "".join(
        f'<th style="border:1px solid #ddd;padding:6px 8px;background:#f2f2f2;text-align:left;">{c}</th>'
        for c in df.columns
    )

    body_rows = []
    for _, row in df.iterrows():
        # row-level tint if failed > 0
        row_failed_val = 0
        if failed_col is not None:
            try:
                row_failed_val = int(row[failed_col]) if pd.notna(row[failed_col]) else 0
            except Exception:
                row_failed_val = 0

        tr_style = 'background:#fff5f5;' if row_failed_val > 0 else ''
        tds = []
        for c in df.columns:
            v = "" if pd.isna(row[c]) else row[c]
            tds.append(
                f'<td style="border:1px solid #ddd;padding:6px 8px;text-align:left;">{fmt_cell(v, c)}</td>'
            )
        body_rows.append(f'<tr style="{tr_style}">' + "".join(tds) + "</tr>")

    table_html = f"""
    <h3>{title}</h3>
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>
        {''.join(body_rows)}
      </tbody>
    </table>
    """
    return table_html

def send_email_report(
    recipients,
    subject,
    overall_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    failed_df: pd.DataFrame,
    # NEW: identifiers shown at top
    parent_request_id=None,
    scenario_id=None,
    lob=None,
    sender="saisrikar.ravipati@cvshealth.com",
    smtp_host="smtppaz.corp.cvscaremark.com",
    smtp_port=25,
    use_starttls=True
):
    # --- Identifiers block (only show what is provided) ---
    ident_lines = []
    if parent_request_id:
        ident_lines.append(f"<b>PARENT_REQUEST_ID:</b> {parent_request_id}")
    if scenario_id:
        ident_lines.append(f"<b>SCENARIO_ID:</b> {scenario_id}")
    if lob:
        ident_lines.append(f"<b>LOB:</b> {lob}")
    ident_html = ""
    if ident_lines:
        ident_html = """
        <div style="border:1px solid #ddd;background:#f7f7f7;padding:10px 12px;
                    font-family:Arial,sans-serif;font-size:13px;border-radius:6px;margin-bottom:12px;">
          {lines}
        </div>
        """.format(lines="<br/>".join(ident_lines))

    # --- Overall Summary inline with colors ---
    overall_html = _overall_summary_to_html(overall_df, title="Overall Summary")

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;">
        <p>Hello Team,</p>
        {ident_html}
        <p>Below is the Overall Summary for this run:</p>
        {overall_html}
        <p style="margin-top:12px;">Attached: Summary All DF and Failed DFS DF as Excel files.</p>
        <p>Thanks!</p>
      </body>
    </html>
    """

    # --- Attachments as Excel ---
    attachments = []
    if summary_df is not None:
        attachments.append(("summary_all_df.xlsx", _df_to_excel_bytes(summary_df, "summary_all")))
    if failed_df is not None:
        attachments.append(("failed_dfs_df.xlsx", _df_to_excel_bytes(failed_df, "failed_dfs")))

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    for fname, fbytes in attachments:
        part = MIMEApplication(fbytes, Name=fname)
        part["Content-Disposition"] = f'attachment; filename="{fname}"'
        msg.attach(part)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_starttls:
                try:
                    server.starttls()
                except Exception:
                    pass
            server.sendmail(sender, recipients, msg.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

# ----------------------------
# USAGE EXAMPLE
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
    failed_df=fail_dfs_df,
    parent_request_id=parent_request_id,  # <-- your variable
    scenario_id=scenario_id,              # <-- your variable
    lob=lob_id                            # <-- your variable (or lob)
)
