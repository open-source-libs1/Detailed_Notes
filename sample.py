import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _one_model_table_html(model_df: pd.DataFrame) -> str:
    """
    Render a single model's summary table with:
      - green Passed
      - red Failed
      - FINAL TOTAL row inside the table (no stray numbers outside).
    Expects columns: Table, Total_Tests, Passed, Failed
    """
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
        "Total_Tests": df["Total_Tests"].sum() if "Total_Tests" in df.columns else "",
        "Passed": df["Passed"].sum() if "Passed" in df.columns else "",
        "Failed": df["Failed"].sum() if "Failed" in df.columns else "",
    }
    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

    passed_col = "Passed"
    failed_col = "Failed"

    def fmt_cell(val, col, is_total):
        # totals bolded
        weight = "700" if is_total else "400"
        color = None

        if col == passed_col:
            color = "#1a7f37"   # green
        elif col == failed_col:
            color = "#d1242f"   # red

        inner = str(val)
        style_bits = [f"font-weight:{weight};"]
        if color:
            style_bits.append(f"color:{color};")
        style = "".join(style_bits)
        return f'<span style="{style}">{inner}</span>'

    header_cells = "".join(
        f'<th style="border:1px solid #ddd;padding:6px 8px;background:#f2f2f2;text-align:left;">{c}</th>'
        for c in df.columns
    )

    body_rows = []
    last_index = len(df) - 1

    for idx, row in df.iterrows():
        is_total = idx == last_index

        # Row shading: regular rows red-tinted if Failed>0; TOTAL row light grey.
        if is_total:
            tr_style = 'background:#f0f0f0;'
            row_failed_val = 0
        else:
            row_failed_val = int(row.get(failed_col, 0) or 0)
            tr_style = 'background:#fff5f5;' if row_failed_val > 0 else ''

        tds = []
        for c in df.columns:
            v = "" if pd.isna(row[c]) else row[c]
            tds.append(
                f'<td style="border:1px solid #ddd;padding:6px 8px;text-align:left;">'
                f'{fmt_cell(v, c, is_total)}'
                f'</td>'
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
    For each (uw_req_id, scenario_id, lob) group, render:
      - Light-blue ID card.
      - Grey 'Report Path' card (per model).
      - Result table (with TOT row).
    """
    if summary_df is None or summary_df.empty:
        return "<p><i>No summary results to report.</i></p>"

    # group per model
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

        # ---- per-model Report Path card (grey) ----
        report_html = ""
        if "report_path" in g.columns:
            vals = [str(v).strip() for v in g["report_path"].dropna().unique() if str(v).strip()]
            if vals:
                report_path = vals[0]
                # leave as plain text/monospace; user can copy path
                report_html = f"""
                <div style="border:1px solid #ddd;background:#f7f7f7;padding:10px 12px;
                            font-family:Arial,sans-serif;font-size:13px;border-radius:6px;
                            margin:0 0 8px 0;">
                  <b>Report Path:</b><br/>
                  <code>{report_path}</code>
                </div>
                """

        # ---- result table (only table cols) ----
        model_table_df = g[["Table", "Total_Tests", "Passed", "Failed"]].copy()

        blocks.append(header_html + report_html + _one_model_table_html(model_table_df))

    return "".join(blocks)


def send_summary_email_grouped(
    recipients,
    subject,
    summary_df: pd.DataFrame,
    debug_notebook_url: str | None = None,   # <-- NEW: common debug notebook link
    sender="saisrikar.ravipati@cvshealth.com",
    smtp_host="smtppaz.corp.cvscaremark.com",
    smtp_port=25,
    use_starttls=True,
):
    """
    Send grouped summary email:
      - per-model ID + report path + table
      - optional single Debug Notebook link at the bottom.
    """
    grouped_html = _summary_df_grouped_html(summary_df)

    # Optional global debug notebook card at bottom
    debug_html = ""
    if debug_notebook_url:
        link_html = (
            f'<a href="{debug_notebook_url}">{debug_notebook_url}</a>'
            if debug_notebook_url.lower().startswith("http")
            else f"<code>{debug_notebook_url}</code>"
        )
        debug_html = f"""
        <div style="border:1px solid #ddd;background:#f7f7f7;padding:10px 12px;
                    font-family:Arial,sans-serif;font-size:13px;border-radius:6px;
                    margin:14px 0 8px 0;">
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
