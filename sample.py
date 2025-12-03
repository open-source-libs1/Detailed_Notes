import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# -------------------------------------------------------------------
# Config: which tables are "input"
# -------------------------------------------------------------------
INPUT_TABLE_NAMES = {
    "SrxClaims Compare",
    "Rebate Compare",
    "Revenue Compare",
}

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _ensure_summary_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to: Table, Total_Tests, Passed, Failed, uw_req_id, scenario_id, lob, report_path."""
    if df.empty:
        return df

    col_map = {}
    for c in df.columns:
        lc = c.lower()
        if lc == "table":
            col_map[c] = "Table"
        elif lc in ("total_tests", "total_test", "total_test_cnt"):
            col_map[c] = "Total_Tests"
        elif lc == "passed":
            col_map[c] = "Passed"
        elif lc == "failed":
            col_map[c] = "Failed"
        else:
            col_map.setdefault(c, c)

    df = df.rename(columns=col_map)

    for c in ["Total_Tests", "Passed", "Failed"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    return df


def _render_input_table(input_df: pd.DataFrame) -> str:
    """Render the small input table: Table / Total_Tests / Passed / Failed / Status."""
    if input_df.empty:
        return "<p><i>No input tables.</i></p>"

    df = input_df.copy()
    # Add Status: PASSED if Failed==0 else FAILED
    df["Status"] = df["Failed"].apply(lambda x: "PASSED" if x == 0 else "FAILED")

    cols = ["Table", "Total_Tests", "Passed", "Failed", "Status"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

    def fmt_cell(val, col):
        if col == "Passed":
            return f'<span style="color:#1a7f37;font-weight:600;">{val}</span>'
        if col == "Failed":
            return f'<span style="color:#d1242f;font-weight:600;">{val}</span>'
        if col == "Status":
            color = "#1a7f37" if val == "PASSED" else "#d1242f"
            return f'<span style="color:{color};font-weight:700;">{val}</span>'
        return str(val)

    header_cells = "".join(
        f'<th style="border:1px solid #ddd;padding:6px 8px;background:#f2f2f2;">{c}</th>'
        for c in df.columns
    )

    body_rows = []
    for _, row in df.iterrows():
        tds = []
        for c in df.columns:
            v = "" if pd.isna(row[c]) else row[c]
            tds.append(
                f'<td style="border:1px solid #ddd;padding:6px 8px;">{fmt_cell(v, c)}</td>'
            )
        body_rows.append("<tr>" + "".join(tds) + "</tr>")

    return f"""
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;width:100%;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def _render_output_table(output_df: pd.DataFrame) -> str:
    """Render output table (pnl_* etc) with TOTAL row and Passed/Failed coloring."""
    if output_df.empty:
        return "<p><i>No output tables.</i></p>"

    df = output_df.copy()

    # TOTAL row
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

    header_cells = "".join(
        f'<th style="border:1px solid #ddd;padding:6px 8px;background:#f2f2f2;">{c}</th>'
        for c in df.columns
    )

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
            v = "" if pd.isna(row[c]) else row[c]
            tds.append(
                f'<td style="border:1px solid #ddd;padding:6px 8px;">'
                f'{fmt_cell(v, c, is_total)}'
                f'</td>'
            )
        body_rows.append(f'<tr style="{tr_style}">{"".join(tds)}</tr>')

    return f"""
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;width:100%;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def _summary_df_grouped_html(summary_df: pd.DataFrame) -> str:
    """
    Per model:
      - blue ID card
      - Input Report Path + input table
      - Output Report Path + output table
    """
    if summary_df is None or summary_df.empty:
        return "<p><i>No summary results to report.</i></p>"

    df = _ensure_summary_cols(summary_df)

    group_cols = ["uw_req_id", "scenario_id", "lob"]
    grouped = df.groupby(group_cols, dropna=False, as_index=False)

    blocks = []

    for (uw, sid, lob), g in grouped:
        # split input vs output by table name
        input_mask = g["Table"].isin(INPUT_TABLE_NAMES)
        input_df = g[input_mask].copy()
        output_df = g[~input_mask].copy()

        # ---- ID card (blue) ----
        id_card = f"""
        <div style="border:1px solid #99c2ff;background:#e6f2ff;
                    padding:10px 12px;margin:14px 0 6px 0;
                    font-family:Arial;font-size:13px;border-radius:6px;">
          <b>PARENT_REQUEST_ID:</b> {uw}<br/>
          <b>SCENARIO_ID:</b> {sid}<br/>
          <b>LOB:</b> {lob}
        </div>
        """

        # ---- Input section ----
        input_html = ""
        if not input_df.empty:
            # assume same report_path for all input rows in this model
            in_path = None
            if "report_path" in input_df.columns:
                paths = [p for p in input_df["report_path"].dropna().unique() if str(p).strip()]
                if paths:
                    in_path = paths[0]

            if in_path:
                input_html += f"""
                <div style="border:1px solid #ddd;background:#f7f7f7;
                            padding:10px 12px;margin:0 0 6px 0;
                            font-family:Arial;font-size:13px;border-radius:6px;">
                  <b>Input Report Path:</b><br/>
                  <code>{in_path}</code>
                </div>
                """

            input_html += "<b>Input Tables</b>" + _render_input_table(input_df)

        # ---- Output section ----
        output_html = ""
        if not output_df.empty:
            out_path = None
            if "report_path" in output_df.columns:
                paths = [p for p in output_df["report_path"].dropna().unique() if str(p).strip()]
                if paths:
                    out_path = paths[0]

            if out_path:
                output_html += f"""
                <div style="border:1px solid #ddd;background:#f7f7f7;
                            padding:10px 12px;margin:8px 0 6px 0;
                            font-family:Arial;font-size:13px;border-radius:6px;">
                  <b>Output Report Path:</b><br/>
                  <code>{out_path}</code>
                </div>
                """

            output_html += "<b>Output Tables</b>" + _render_output_table(output_df)

        blocks.append(id_card + input_html + output_html)

    return "".join(blocks)


# -------------------------------------------------------------------
# Send email
# -------------------------------------------------------------------
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
