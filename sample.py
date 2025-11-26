import pandas as pd

def build_summary_df_from_log(log_data):
    """
    Walk log_data sequentially.
    Attach current context (uw_req_id, scenario_id, lob, report_path, etc.)
    to each table-level summary entry.
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
        "report_path": None,     # <-- NEW
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
        if not isinstance(d, dict):
            return False
        if "Table" in d and d.get("Total_Tests") is not None:
            return False
        return any(k in d for k in [
            "uw_req_id", "scenario_id", "lob",
            "run_id", "start_time", "end_time", "duration",
            "report_path",                      # <-- NEW
            "PARENT_REQUEST_ID", "SCENARIO_ID", "LOB"
        ])

    for item in log_data:
        if not isinstance(item, dict):
            continue

        # Update context from metadata-like records
        if is_ctx_row(item):
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

            # NEW — capture report_path per run
            if "report_path" in item and item["report_path"]:
                ctx["report_path"] = item["report_path"]

        # Capture table summaries
        if is_summary_row(item):
            row = dict(item)
            row["uw_req_id"] = row.get("uw_req_id") or ctx["uw_req_id"]
            row["scenario_id"] = row.get("scenario_id") or ctx["scenario_id"]
            row["lob"] = row.get("lob") if row.get("lob") is not None else ctx["lob"]
            row["run_id"] = row.get("run_id") or ctx["run_id"]
            row["start_time"] = row.get("start_time") or ctx["start_time"]
            row["end_time"] = row.get("end_time") or ctx["end_time"]
            row["duration"] = row.get("duration") or ctx["duration"]
            row["report_path"] = row.get("report_path") or ctx["report_path"]   # <-- NEW

            summary_rows.append(row)

    df = pd.DataFrame(summary_rows)

    if df.empty:
        return df

    # Normalize numeric columns
    for c in ["Total_Tests", "Passed", "Failed"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # Keep final meaningful columns
    keep_cols = [
        "Table", "Total_Tests", "Passed", "Failed",
        "uw_req_id", "scenario_id", "lob",
        "report_path"             # <-- NEW
    ]
    df = df[[c for c in keep_cols if c in df.columns]]

    return df
