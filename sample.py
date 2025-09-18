# --- Config (adjust names only if your cols differ) ---------------------------
GROUP_KEYS   = ["PARENT_REQUEST_ID", "APP_ID", "LOB"]
DISPLAY_COLS = ["TEST_DESC", "EXECUTION_STATUS", "TOTAL_CNT", "SUCCESS_CNT", "FAILURE_CNT"]
ORDER_IN_GROUP = ["TEST_DESC"]  # secondary sort inside each group

# If upstream names differ, map them here → standard names above
RENAME = {
    # "TS_STATUS": "EXECUTION_STATUS",
    # "SUCCESS_S_CNT": "SUCCESS_CNT",
    # "FAIL_CNT": "FAILURE_CNT",
}

# --- Normalize columns / derive missing counts --------------------------------
import pandas as pd
from html import escape as _esc

df = email_table.copy()
if RENAME:
    df = df.rename(columns=RENAME)

# Derive success/failure if one is missing
if "SUCCESS_CNT" not in df.columns and {"TOTAL_CNT", "FAILURE_CNT"} <= set(df.columns):
    df["SUCCESS_CNT"] = df["TOTAL_CNT"] - df["FAILURE_CNT"]
if "FAILURE_CNT" not in df.columns and {"TOTAL_CNT", "SUCCESS_CNT"} <= set(df.columns):
    df["FAILURE_CNT"] = df["TOTAL_CNT"] - df["SUCCESS_CNT"]

needed = list(dict.fromkeys(GROUP_KEYS + DISPLAY_COLS))  # keep order, drop dups
missing = [c for c in needed if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns for email rendering: {missing}. "
                     f"Available: {sorted(df.columns.tolist())}")

# Keep only needed columns and sort for stable, readable output
df = df[needed].copy()

# Ensure numeric columns are ints for clean HTML
for c in ["TOTAL_CNT", "SUCCESS_CNT", "FAILURE_CNT"]:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")

sort_cols = GROUP_KEYS + [c for c in ORDER_IN_GROUP if c in df.columns]
df = df.sort_values(sort_cols, kind="stable").reset_index(drop=True)

# --- Styles (inline CSS is safest for email clients) --------------------------
CSS = """
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
  h3{margin:0 0 10px}
  h4{margin:14px 0 6px}
  .kv{font-size:13px;margin:0 0 6px}
  .divider{margin:12px 0;border:none;border-top:1px solid #e5e7eb}
  table.regtable{border-collapse:collapse;width:860px;max-width:100%}
  .regtable th,.regtable td{border:1px solid #e5e7eb;padding:6px 8px;text-align:center}
  .regtable th{background:#f8fafc;text-transform:uppercase;font-size:12px;letter-spacing:.02em}
  .good{color:#0e7c2f;font-weight:600}
  .bad{color:#b00020;font-weight:600}
  .bg-good{background:#f2fff5}
  .bg-bad{background:#fff2f3}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
</style>
"""

# --- HTML rendering helpers ---------------------------------------------------
def _render_table_block(keys_dict: dict, gdf: pd.DataFrame, display_cols: list[str]) -> str:
    # Header with the 3 key fields
    header = (
        "<h4>Group</h4>"
        f"<p class='kv'>{GROUP_KEYS[0]}: <span class='mono'>{_esc(str(keys_dict[GROUP_KEYS[0]]))}</span> "
        f"&nbsp;|&nbsp; {GROUP_KEYS[1]}: <span class='mono'>{_esc(str(keys_dict[GROUP_KEYS[1]]))}</span> "
        f"&nbsp;|&nbsp; {GROUP_KEYS[2]}: <span class='mono'>{_esc(str(keys_dict[GROUP_KEYS[2]]))}</span></p>"
    )

    # Table head
    thead = "<thead><tr>" + "".join(f"<th>{_esc(col)}</th>" for col in display_cols) + "</tr></thead>"

    # Table rows with conditional coloring
    rows_html = []
    for _, row in gdf[display_cols].iterrows():
        failure_cnt = int(row.get("FAILURE_CNT", 0)) if str(row.get("FAILURE_CNT", "")).strip() != "" else 0
        total_cnt   = int(row.get("TOTAL_CNT", -1)) if str(row.get("TOTAL_CNT", "")).strip() != "" else -1
        success_cnt = int(row.get("SUCCESS_CNT", -1)) if str(row.get("SUCCESS_CNT", "")).strip() != "" else -1

        # row bg: red if any failures, green if all success, neutral otherwise
        row_cls = "bg-bad" if failure_cnt > 0 else ("bg-good" if total_cnt >= 0 and success_cnt == total_cnt else "")
        tds = []
        for col in display_cols:
            val = row[col]
            if col == "EXECUTION_STATUS":
                s = str(val).upper()
                status_cls = "bad" if "FAIL" in s else ("good" if s in ("COMPLETED", "PASS") else "")
                tds.append(f"<td class='{status_cls}'>{_esc(str(val))}</td>")
            else:
                tds.append(f"<td>{_esc(str(val))}</td>")
        rows_html.append(f"<tr class='{row_cls}'>" + "".join(tds) + "</tr>")

    tbody = "<tbody>" + "".join(rows_html) + "</tbody>"
    return header + f"<table class='regtable'>{thead}{tbody}</table>"

# --- Build the per-group sections --------------------------------------------
sections = []
for keys, g in df.groupby(GROUP_KEYS, dropna=False, sort=False):
    key_vals = dict(zip(GROUP_KEYS, keys))
    sections.append(_render_table_block(key_vals, g, [c for c in DISPLAY_COLS if c in g.columns]))

# --- Final HTML body + CSV attachment bytes ----------------------------------
html_body = f"""
<html>
  <head>{CSS}</head>
  <body>
    <h3>QAAP Daily Regression – Integrated Tests</h3>
    <p>Validations: {len(df)}</p>
    {'<hr class="divider">'.join(sections)}
  </body>
</html>
"""

# CSV uses the same sorted frame so the order matches the email
csv_bytes = df.to_csv(index=False).encode("utf-8")

# Example usage with your mail helper:
# send_email(subject="QAAP Daily Regression – Integrated Tests",
#            html_body=html_body,
#            attachments=[("ce_regression_summary_daily_result.csv", csv_bytes)])
