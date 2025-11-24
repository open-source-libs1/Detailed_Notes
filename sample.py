import pandas as pd

def build_summary_df_from_log(log_data):
    """
    Walk log_data sequentially.
    - Track current context (uw_req_id, scenario_id, lob, run_id, times, etc.)
      from metadata-like records.
    - For each table summary record, attach the *current* context
      unless that record already has explicit values.
    """
    if not log_data:
        return pd.DataFrame()

    summary_rows = []

    # context that can change per run
    ctx = {
        "uw_req_id": None,
        "scenario_id": None,
        "lob": None,
        "run_id": None,
        "start_time": None,
        "end_time": None,
        "duration": None,
    }

    def is_summary_row(d):
        return (
            isinstance(d, dict)
            and d.get("Table") is not None
            and "Total_Tests" in d
            and "Passed" in d
            and "Failed" in d
        )

    def is_ctx_row(d):
        # any record that carries IDs/time/run info but not Table summary
        if not isinstance(d, dict):
            return False
        if "Table" in d and d.get("Total_Tests") is not None:
            return False
        return any(k in d for k in ["uw_req_id", "scenario_id", "lob", "run_id", "start_time", "end_time", "duration",
                                    "PARENT_REQUEST_ID", "SCENARIO_ID", "LOB"])

    for item in log_data:
        if not isinstance(item, dict):
            continue

        # Update context from metadata rows
        if is_ctx_row(item):
            # support both old and new key names just in case
            if "uw_req_id" in item and item["uw_req_id"]:
                ctx["uw_req_id"] = item["uw_req_id"]
            if "PARENT_REQUEST_ID" in item and item["PARENT_REQUEST_ID"]:
                ctx["uw_req_id"] = item["PARENT_REQUEST_ID"]

            if "scenario_id" in item and item["scenario_id"]:
                ctx["scenario_id"] = item["scenario_id"]
            if "SCENARIO_ID" in item and item["SCENARIO_ID"]:
                ctx["scenario_id"] = item["SCENARIO_ID"]

            if "lob" in item and item["lob"] is not None:
                ctx["lob"] = item["lob"]
            if "LOB" in item and item["LOB"] is not None:
                ctx["lob"] = item["LOB"]

            for k in ["run_id", "start_time", "end_time", "duration"]:
                if k in item and item[k] is not None:
                    ctx[k] = item[k]

        # Collect summary rows
        if is_summary_row(item):
            row = dict(item)  # copy

            # attach context only if missing in the row
            row["uw_req_id"] = row.get("uw_req_id") or ctx["uw_req_id"]
            row["scenario_id"] = row.get("scenario_id") or ctx["scenario_id"]
            row["lob"] = row.get("lob") if row.get("lob") is not None else ctx["lob"]
            row["run_id"] = row.get("run_id") or ctx["run_id"]
            row["start_time"] = row.get("start_time") or ctx["start_time"]
            row["end_time"] = row.get("end_time") or ctx["end_time"]
            row["duration"] = row.get("duration") or ctx["duration"]

            summary_rows.append(row)

    df = pd.DataFrame(summary_rows)

    if df.empty:
        return df

    # normalize numeric cols
    for c in ["Total_Tests", "Passed", "Failed"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # keep only what you want
    keep_cols = ["Table", "Total_Tests", "Passed", "Failed", "uw_req_id", "scenario_id", "lob"]
    df = df[[c for c in keep_cols if c in df.columns]]

    return df


////////////////////////



import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _one_model_table_html(model_df: pd.DataFrame) -> str:
    """
    Renders a single model's summary table with green Passed / red Failed.
    Expects columns: Table, Total_Tests, Passed, Failed
    """
    if model_df.empty:
        return "<p><i>No rows.</i></p>"

    passed_col = "Passed"
    failed_col = "Failed"

    def fmt_cell(val, col):
        if col == passed_col:
            return f'<span style="color:#1a7f37;font-weight:700;">{val}</span>'
        if col == failed_col:
            return f'<span style="color:#d1242f;font-weight:700;">{val}</span>'
        return str(val)

    header_cells = "".join(
        f'<th style="border:1px solid #ddd;padding:6px 8px;background:#f2f2f2;text-align:left;">{c}</th>'
        for c in model_df.columns
    )

    body_rows = []
    for _, row in model_df.iterrows():
        # light red tint if failures > 0
        row_failed_val = int(row.get(failed_col, 0) or 0)
        tr_style = 'background:#fff5f5;' if row_failed_val > 0 else ''

        tds = []
        for c in model_df.columns:
            v = "" if pd.isna(row[c]) else row[c]
            tds.append(
                f'<td style="border:1px solid #ddd;padding:6px 8px;text-align:left;">{fmt_cell(v, c)}</td>'
            )
        body_rows.append(f'<tr style="{tr_style}">' + "".join(tds) + "</tr>")

    return f"""
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px; width:100%;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def _summary_df_grouped_html(summary_df: pd.DataFrame) -> str:
    """
    Splits summary_df per model (uw_req_id, scenario_id, lob) and renders:
      - a header block with identifiers
      - a table underneath (Table, Total_Tests, Passed, Failed)
    """
    if summary_df is None or summary_df.empty:
        return "<p><i>No summary results to report.</i></p>"

    # Ensure numeric cols are ints
    for c in ["Total_Tests", "Passed", "Failed"]:
        summary_df[c] = pd.to_numeric(summary_df[c], errors="coerce").fillna(0).astype(int)

    # Group per model
    group_cols = ["uw_req_id", "scenario_id", "lob"]
    grouped = summary_df.groupby(group_cols, dropna=False, as_index=False)

    blocks = []
    for (uw, sid, lob), g in grouped:
        # model header (like your image 2)
        header_html = f"""
        <div style="border:1px solid #ddd;background:#f7f7f7;padding:10px 12px;
                    font-family:Arial,sans-serif;font-size:13px;border-radius:6px;margin:14px 0 8px 0;">
          <b>PARENT_REQUEST_ID:</b> {uw}<br/>
          <b>SCENARIO_ID:</b> {sid}<br/>
          <b>LOB:</b> {lob}
        </div>
        """

        # Table for this model (no identifiers inside the table)
        model_table_df = g[["Table", "Total_Tests", "Passed", "Failed"]].copy()

        blocks.append(header_html + _one_model_table_html(model_table_df))

    return "".join(blocks)


def send_summary_email_grouped(
    recipients,
    subject,
    summary_df: pd.DataFrame,
    sender="saisrikar.ravipati@cvshealth.com",
    smtp_host="smtppaz.corp.cvscaremark.com",
    smtp_port=25,
    use_starttls=True
):
    """
    Send email grouped per model from summary_df.
    No extra parameters for IDs; pulled from summary_df itself.
    No attachments.
    """

    grouped_html = _summary_df_grouped_html(summary_df)

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;">
        <p>Hello Team,</p>
        <p>Below are the Overall Summaries for this run (grouped per model):</p>
        {grouped_html}
        <p style="margin-top:12px;">Thanks!</p>
      </body>
    </html>
    """

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

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


