import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _one_model_table_html(model_df: pd.DataFrame) -> str:
    """Renders a single model's summary table with green Passed / red Failed."""
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
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;width:100%;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def _summary_df_grouped_html(summary_df: pd.DataFrame) -> str:
    """
    For each (uw_req_id, scenario_id, lob) group:
      - Light blue card with IDs
      - Grey card with report path / debug notebook link
      - Result table under it
    Expects columns: Table, Total_Tests, Passed, Failed, uw_req_id, scenario_id, lob, [report_path]
    """
    if summary_df is None or summary_df.empty:
        return "<p><i>No summary results to report.</i></p>"

    # ensure ints
    for c in ["Total_Tests", "Passed", "Failed"]:
        if c in summary_df.columns:
            summary_df[c] = pd.to_numeric(summary_df[c], errors="coerce").fillna(0).astype(int)

    group_cols = ["uw_req_id", "scenario_id", "lob"]
    grouped = summary_df.groupby(group_cols, dropna=False, as_index=False)

    blocks = []
    for (uw, sid, lob), g in grouped:
        # ---- ID card (light blue) ----
        header_html = f"""
        <div style="border:1px solid #99c2ff;background:#e6f2ff;padding:10px 12px;
                    font-family:Arial,sans-serif;font-size:13px;border-radius:6px;
                    margin:14px 0 6px 0;">
          <b>PARENT_REQUEST_ID:</b> {uw}<br/>
          <b>SCENARIO_ID:</b> {sid}<br/>
          <b>LOB:</b> {lob}
        </div>
        """

        # ---- report path / debug notebook card ----
        report_html = ""
        if "report_path" in g.columns:
            vals = [str(v).strip() for v in g["report_path"].dropna().unique() if str(v).strip()]
            if vals:
                report_path = vals[0]
                if report_path.lower().startswith("http"):
                    link_html = f'<a href="{report_path}">{report_path}</a>'
                else:
                    link_html = f'<code>{report_path}</code>'

                report_html = f"""
                <div style="border:1px solid #ddd;background:#f7f7f7;padding:10px 12px;
                            font-family:Arial,sans-serif;font-size:13px;border-radius:6px;
                            margin:0 0 8px 0;">
                  <b>Debug Notebook (run for this model / check fail_dfs_df):</b><br/>
                  {link_html}
                </div>
                """

        # ---- table (only table columns) ----
        model_table_df = g[["Table", "Total_Tests", "Passed", "Failed"]].copy()

        blocks.append(header_html + report_html + _one_model_table_html(model_table_df))

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
    """Send grouped summary email with ID card + report path + table per model."""
    grouped_html = _summary_df_grouped_html(summary_df)

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;">
        <p>Hi Team,</p>
        <p>Below are the High level accuracy tests on Output Tables:</p>
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
