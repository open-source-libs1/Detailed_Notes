import pandas as pd

def build_summary_df_from_log(log_data):
    """
    Build a flat summary DataFrame from log_data.

    Handles both input and output tables.
    Output columns:
      Table, Total_Tests, Passed, Failed, uw_req_id, scenario_id, lob, report_path
    """

    if not log_data:
        return pd.DataFrame(
            columns=["Table", "Total_Tests", "Passed", "Failed",
                     "uw_req_id", "scenario_id", "lob", "report_path"]
        )

    summary_rows = []

    # context that can change per run/model
    ctx = {
        "uw_req_id": None,
        "scenario_id": None,
        "lob": None,
        "report_path": None,
    }

    def _get_first(d: dict, keys, default=None):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    def _is_summary_row(d: dict) -> bool:
        if not isinstance(d, dict):
            return False
        has_table = any(k in d for k in ("Table", "table"))
        has_total = any(k in d for k in ("Total_Tests", "Total_tests", "total_tests",
                                         "Total_test", "total_test"))
        has_pass = any(k in d for k in ("Passed", "passed"))
        has_fail = any(k in d for k in ("Failed", "failed"))
        return has_table and has_total and has_pass and has_fail

    def _is_ctx_row(d: dict) -> bool:
        if not isinstance(d, dict):
            return False
        if _is_summary_row(d):
            return False
        keys = (
            "uw_req_id", "UW_REQ_ID", "PARENT_REQUEST_ID", "parent_request_id",
            "scenario_id", "SCENARIO_ID", "APP_ID", "app_id",
            "lob", "LOB",
            "report_path",
        )
        return any(k in d for k in keys)

    for item in log_data:
        if not isinstance(item, dict):
            continue

        # 1) update context from metadata-only rows
        if _is_ctx_row(item):
            uw = _get_first(item, ["uw_req_id", "UW_REQ_ID", "PARENT_REQUEST_ID", "parent_request_id"])
            sid = _get_first(item, ["scenario_id", "SCENARIO_ID", "APP_ID", "app_id"])
            lob = _get_first(item, ["lob", "LOB"])
            rpt = _get_first(item, ["report_path"])

            if uw is not None:
                ctx["uw_req_id"] = uw
            if sid is not None:
                ctx["scenario_id"] = sid
            if lob is not None:
                ctx["lob"] = lob
            if rpt is not None:
                ctx["report_path"] = rpt

        # 2) collect summary rows
        if _is_summary_row(item):
            row = {}

            row["Table"] = _get_first(item, ["Table", "table"])

            row["Total_Tests"] = _get_first(
                item,
                ["Total_Tests", "Total_tests", "total_tests", "Total_test", "total_test"],
                default=0,
            )
            row["Passed"] = _get_first(item, ["Passed", "passed"], default=0)
            row["Failed"] = _get_first(item, ["Failed", "failed"], default=0)

            row["uw_req_id"] = _get_first(
                item,
                ["uw_req_id", "UW_REQ_ID", "PARENT_REQUEST_ID", "parent_request_id"],
                default=ctx["uw_req_id"],
            )
            row["scenario_id"] = _get_first(
                item,
                ["scenario_id", "SCENARIO_ID", "APP_ID", "app_id"],
                default=ctx["scenario_id"],
            )
            row["lob"] = _get_first(
                item,
                ["lob", "LOB"],
                default=ctx["lob"],
            )
            row["report_path"] = _get_first(
                item,
                ["report_path"],
                default=ctx["report_path"],
            )

            summary_rows.append(row)

    df = pd.DataFrame(summary_rows)

    if df.empty:
        return pd.DataFrame(
            columns=["Table", "Total_Tests", "Passed", "Failed",
                     "uw_req_id", "scenario_id", "lob", "report_path"]
        )

    # numeric types
    for c in ["Total_Tests", "Passed", "Failed"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # ensure all columns exist
    for c in ["uw_req_id", "scenario_id", "lob", "report_path"]:
        if c not in df.columns:
            df[c] = None

    df = df[["Table", "Total_Tests", "Passed", "Failed",
             "uw_req_id", "scenario_id", "lob", "report_path"]]

    return df

# Example:
# summary_df = build_summary_df_from_log(log_data)
# display(summary_df)




/////////////////////////////////////////////

import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# which table names are treated as "input" tables
INPUT_TABLE_NAMES = {
    "SrxClaims Compare",
    "Rebate Compare",
    "Revenue Compare",
}

def _ensure_summary_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    for c in ["Total_Tests", "Passed", "Failed"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    return df

def _render_input_table(input_df: pd.DataFrame) -> str:
    """Input table: Table / Total_Tests / Passed / Failed / Status."""
    if input_df.empty:
        return "<p><i>No input tables.</i></p>"

    df = input_df.copy()
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
    """
    Output tables: ONLY Table, Total_Tests, Passed, Failed
    + TOTAL row, Passed/Failed colored.
    """
    if output_df.empty:
        return "<p><i>No output tables.</i></p>"

    # keep only needed columns
    df = output_df[["Table", "Total_Tests", "Passed", "Failed"]].copy()

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
    For each model (uw_req_id, scenario_id, lob):
      - ID block (blue)
      - Input section: Input Report Path + input table
      - Output section: Output Report Path + output table (trimmed cols)
    """
    if summary_df is None or summary_df.empty:
        return "<p><i>No summary results to report.</i></p>"

    df = _ensure_summary_cols(summary_df)

    group_cols = ["uw_req_id", "scenario_id", "lob"]
    grouped = df.groupby(group_cols, dropna=False, as_index=False)

    blocks = []

    for (uw, sid, lob), g in grouped:
        input_mask = g["Table"].isin(INPUT_TABLE_NAMES)
        input_df = g[input_mask].copy()
        output_df = g[~input_mask].copy()

        # ID card
        id_card = f"""
        <div style="border:1px solid #99c2ff;background:#e6f2ff;
                    padding:10px 12px;margin:14px 0 6px 0;
                    font-family:Arial;font-size:13px;border-radius:6px;">
          <b>PARENT_REQUEST_ID:</b> {uw}<br/>
          <b>SCENARIO_ID:</b> {sid}<br/>
          <b>LOB:</b> {lob}
        </div>
        """

        # Input section
        input_html = ""
        if not input_df.empty:
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

        # Output section
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

def send_summary_email_grouped(
    recipients,
    subject,
    summary_df: pd.DataFrame,
    debug_notebook_url_1=None,
    debug_notebook_url_2=None,
    sender="saisrikar.ravipati@cvshealth.com",
    smtp_host="smtppaz.corp.cvscaremark.com",
    smtp_port=25,
    use_starttls=True,
):
    grouped_html = _summary_df_grouped_html(summary_df)

    # Build up to two debug cards at the bottom
    debug_html_parts = []

    for idx, url in enumerate([debug_notebook_url_1, debug_notebook_url_2], start=1):
        if not url:
            continue
        if url.lower().startswith("http"):
            link_html = f'<a href="{url}">{url}</a>'
        else:
            link_html = f"<code>{url}</code>"

        debug_html_parts.append(f"""
        <div style="border:1px solid #ddd;background:#f7f7f7;
                    padding:10px 12px;margin:10px 0 4px 0;
                    font-family:Arial;font-size:13px;border-radius:6px;">
          <b>Debug Notebook {idx} (run for a model / check fail_dfs_df):</b><br/>
          {link_html}
        </div>
        """)

    debug_html = "".join(debug_html_parts)

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




///////////////////////////////

summary_df = build_summary_df_from_log(log_data)

send_summary_email_grouped(
    recipients=[...],
    subject=f"QAAP Daily Regression | Integrated Tests - {cluster_name}",
    summary_df=summary_df,
    debug_notebook_url_1="https://adb-.../notebook1",
    debug_notebook_url_2="https://adb-.../notebook2",
)




