# ===================== RENDER EMAIL HTML + CSV ===============================
import pandas as pd
from html import escape as _esc

# ---- Config -----------------------------------------------------------------
GROUP_KEYS     = ["PARENT_REQUEST_ID", "APP_ID", "LOB"]
DISPLAY_COLS   = ["TEST_DESC", "EXECUTION_STATUS", "TOTAL_CNT", "SUCCESS_CNT", "FAILURE_CNT"]
ORDER_IN_GROUP = ["TEST_DESC"]  # secondary sort within a model block

# Optional remaps if upstream names differ. Leave empty if not needed.
RENAME = {
    # "TS_STATUS": "EXECUTION_STATUS",
    # "SUCCESS_S_CNT": "SUCCESS_CNT",
    # "FAIL_CNT": "FAILURE_CNT",
}

# ---- Normalize & prepare dataframe ------------------------------------------
df = email_table.copy()
if RENAME:
    df = df.rename(columns=RENAME)

# Uppercase keys for case-insensitive grouping (preserve blanks)
for k in GROUP_KEYS:
    if k in df.columns:
        df[k] = df[k].where(df[k].notna(), "").astype(str).str.upper()

# Derive missing counts if possible
if "SUCCESS_CNT" not in df.columns and {"TOTAL_CNT", "FAILURE_CNT"} <= set(df.columns):
    df["SUCCESS_CNT"] = df["TOTAL_CNT"] - df["FAILURE_CNT"]
if "FAILURE_CNT" not in df.columns and {"TOTAL_CNT", "SUCCESS_CNT"} <= set(df.columns):
    df["FAILURE_CNT"] = df["TOTAL_CNT"] - df["SUCCESS_CNT"]

# Keep only the columns we need
needed = list(dict.fromkeys(GROUP_KEYS + DISPLAY_COLS))  # ordered de-dupe
missing = [c for c in needed if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns for email rendering: {missing}. "
                     f"Available: {sorted(df.columns.tolist())}")

df = df[needed].copy()

# Ensure numeric columns are clean ints for HTML display
for c in ["TOTAL_CNT", "SUCCESS_CNT", "FAILURE_CNT"]:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")

# Stable sort so CSV and HTML align
sort_cols = GROUP_KEYS + [c for c in ORDER_IN_GROUP if c in df.columns]
df = df.sort_values(sort_cols, kind="stable").reset_index(drop=True)

# ---- CSS (inline for email clients) -----------------------------------------
CSS = """
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
  h3{margin:0 0 10px}
  h4{margin:16px 0 6px}
  /* highlighted key box above each table */
  .kv{
    background:#eef2ff; /* light indigo */
    padding:8px 12px;
    font-size:15px;
    font-weight:700;
    color:#111827;       /* gray-900 */
    border-radius:6px;
    margin:0 0 10px;
    line-height:1.35;
    box-shadow:inset 0 0 0 1px #c7d2fe; /* subtle inner border */
  }
  .divider{margin:16px 0;border:none;border-top:2px solid #d1d5db}
  table.regtable{border-collapse:collapse;width:960px;max-width:100%}
  .regtable th,.regtable td{border:1px solid #e5e7eb;padding:8px 10px;text-align:center}
  .regtable th{
    background:#f8fafc;
    text-transform:uppercase;
    font-size:12px;
    letter-spacing:.02em;
  }
  .good{color:#0e7c2f;font-weight:700}
  .bad{color:#b00020;font-weight:700}
  .bg-good{background:#f2fff5}
  .bg-bad{background:#fff2f3}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
</style>
"""

# ---- HTML builders -----------------------------------------------------------
def _render_table_block(keys_dict: dict, gdf: pd.DataFrame, display_cols: list[str]) -> str:
    # Section header: "Model" + prominent keys box
    header = (
        "<h4>Model</h4>"
        f"<div class='kv'>"
        f"{GROUP_KEYS[0]}: <span class='mono'>{_esc(str(keys_dict.get(GROUP_KEYS[0], '')))}</span><br>"
        f"{GROUP_KEYS[1]}: <span class='mono'>{_esc(str(keys_dict.get(GROUP_KEYS[1], '')))}</span><br>"
        f"{GROUP_KEYS[2]}: <span class='mono'>{_esc(str(keys_dict.get(GROUP_KEYS[2], '')))}</span>"
        f"</div>"
    )

    # Table header
    thead = "<thead><tr>" + "".join(f"<th>{_esc(col)}</th>" for col in display_cols) + "</tr></thead>"

    # Body rows with conditional coloring
    rows_html = []
    for _, row in gdf[display_cols].iterrows():
        # robust int parsing
        def _to_int(x, default=0):
            try:
                return int(str(x).strip())
            except Exception:
                return default

        failure_cnt = _to_int(row.get("FAILURE_CNT", 0), 0)
        total_cnt   = _to_int(row.get("TOTAL_CNT", -1), -1)
        success_cnt = _to_int(row.get("SUCCESS_CNT", -1), -1)

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

# ---- Build sections: one table per (PARENT_REQUEST_ID, APP_ID, LOB) ----------
sections = []
for keys, g in df.groupby(GROUP_KEYS, dropna=False, sort=False):
    keys_dict = dict(zip(GROUP_KEYS, keys))
    sections.append(_render_table_block(keys_dict, g, [c for c in DISPLAY_COLS if c in g.columns]))

# ---- Final HTML body + CSV bytes --------------------------------------------
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

# CSV keeps the same order as the HTML grouping
csv_bytes = df.to_csv(index=False).encode("utf-8")

# Example:
# send_email(subject="QAAP Daily Regression – Integrated Tests",
#            html_body=html_body,
#            attachments=[("ce_regression_summary_daily_result.csv", csv_bytes)])
# ==============================================================================
