import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ------------------------------------------------------------
# TABLE RENDERING (per model)
# ------------------------------------------------------------
def _one_model_table_html(model_df: pd.DataFrame) -> str:
    """Render a table with Passed/Failed highlighting + TOTAL row."""
    if model_df.empty:
        return "<p><i>No rows.</i></p>"

    df = model_df.copy()

    # Ensure numeric
    for c in ["Total_Tests", "Passed", "Failed"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # Add TOTAL row
    total_row = {
        "Table": "TOTAL",
        "Total_Tests": df["Total_Tests"].sum(),
        "Passed": df["Passed"].sum(),
        "Failed": df["Failed"].sum(),
    }
    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

    passed_col = "Passed"
    failed_col = "Failed"

    def fmt_cell(val, col, is_total):
        weight = "700" if is_total else "400"
        color = None
        if col == passed_col:
            color = "#1a7f37"
        elif col == failed_col:
            color = "#d1242f"

        style = f"font-weight:{weight};"
        if color:
            style += f"color:{color};"

        return f'<span style="{style}">{val}</span>'

    # Header
    header_cells = "".join(
        f'<th style="border:1px solid #ddd;padding:6px 8px;background:#f2f2f2;">{c}</th>'
        for c in df.columns
    )

    # Body rows
    body_rows = []
    last_idx = len(df) - 1

    for idx, row in df.iterrows():
        is_total = idx == last_idx

        if is_total:
            tr_style = 'background:#f0f0f0;'
        else:
            fail_val = int(row.get("Failed", 0) or 0)
            tr_style = 'background:#fff5f5;' if fail_val > 0 else ''

        tds = []
        for c in df.columns:
            val = "" if pd.isna(row[c]) else row[c]
            tds.append(
                f'<td style="border:1px solid #ddd;padding:6px 8px;">'
                f'{fmt_cell(val, c, is_total)}'
                f'</td>'
            )
        body_rows.append(f'<tr style="{tr_style}">{"".join(tds)}</tr>')

    return f"""
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;width:100%;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


# ------------------------------------------------------------
# GROUP REPORT RENDERING (per model)
# ------------------------------------------------------------
def _summary_df_grouped_html(summary_df: pd.DataFrame) -> str:
    """
    For each model: ID card + Report Path + Table.
    """
    if summary_df.empty:
        return "<p><i>No summary results to report.</i></p>"

    group_cols = ["uw_req_id", "scenario_id", "lob"]
    grouped = summary_df.groupby(group_cols, dropna=False, as_index=False)

    blocks = []

    for (uw, sid, lob), g in grouped:
        # ---- LIGHT BLUE ID CARD ----
        id_card = f"""
        <div style="border:1px solid #99c2ff;background:#e6f2ff;
                    padding:10px 12px;margin:14px 0 6px 0;
                    font-family:Arial;font-size:13px;border-radius:6px;">
          <b>PARENT_REQUEST_ID:</b> {uw}<br/>
          <b>SCENARIO_ID:</b> {sid}<br/>
          <b>LOB:</b> {lob}
        </div>
        """

        # ---- REPORT PATH (per model) ----
        report_card = ""
        if "report_path" in g.columns:
            paths = [p for p in g["report_path"].dropna().unique() if str(p).strip()]
            if paths:
                p = paths[0]
                report_card = f"""
                <div style="border:1px solid #ddd;background:#f7f7f7;
                            padding:10px 12px;margin:0 0 8px 0;
                            font-family:Arial;font-size:13px;border-radius:6px;">
                  <b>Report Path:</b><br/>
                  <code>{p}</code>
                </div>
                """

        # ---- TABLE FOR THIS MODEL ----
        model_table_df = g[["Table", "Total_Tests", "Passed", "Failed"]].copy()
        table_html = _one_model_table_html(model_table_df)

        blocks.append(id_card + report_card + table_html)

    return "".join(blocks)


# ------------------------------------------------------------
# SEND EMAIL
# ------------------------------------------------------------
def send_summary_email_grouped(
    recipients,
    subject,
    summary_df: pd.DataFrame,
    debug_notebook_url=None,
    sender="saisrikar.ravipati@cvshealth.com",
    smtp_host="smtppaz.corp.cvscaremark.com",
    smtp_port=25,
    use_starttls=True,
):
    grouped_html = _summary_df_grouped_html(summary_df)

    # ---- ONE DEBUG NOTEBOOK BLOCK AT BOTTOM ----
    debug_html = ""
    if debug_notebook_url:
        if debug_notebook_url.lower().startswith("http"):
            link_html = f'<a href="{debug_notebook_url}">{debug_notebook_url}</a>'
        else:
            link_html = f"<code>{debug_notebook_url}</code>"

        debug_html = f"""
        <div style="border:1px solid #ddd;background:#f7f7f7;
                    padding:10px 12px;margin:14px 0 8px 0;
                    font-family:Arial;font-size:13px;border-radius:6px;">
          <b>Debug Notebook (run for a model / check fail_dfs_df):</b><br/>
          {link_html}
        </div>
        """

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;">
        <p>Hi Team,</p>
        <p>Below are the High level accuracy tests on Output Tables:</p>

        {grouped_html}

        {debug_html}

        <p style="margin-top:12px;">Thanks!</p>
      </body>
    </html>
    """

    # ---- SEND ----
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
