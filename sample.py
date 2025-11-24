import pandas as pd

# ------------- 1) Build summary DF from log_data ----------------

def build_summary_df_from_log(log_data):
    """
    log_data: list[dict] mixed (metadata + summary dicts)
    Returns:
      summary_df: detailed per-table summary rows only
    """
    if not log_data:
        return pd.DataFrame()

    df = pd.DataFrame(log_data)

    # Keep only summary rows (must have these columns)
    required_cols = {"Table", "Total_Tests", "Passed", "Failed"}
    present_cols = set(df.columns)

    if not required_cols.issubset(present_cols):
        # try case-insensitive match if columns came in with diff case
        lower_map = {c.lower(): c for c in df.columns}
        req_lower = {c.lower() for c in required_cols}
        if req_lower.issubset(set(lower_map.keys())):
            df = df.rename(columns={lower_map[k]: k.title().replace("_", "_") for k in req_lower})
        else:
            return pd.DataFrame()

    # Filter to only those rows where Table is not null
    df = df[df["Table"].notna()].copy()

    # Normalize types
    for c in ["Total_Tests", "Passed", "Failed"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # Ensure identifier cols exist (in case some runs didn't add them)
    for c in ["uw_req_id", "scenario_id", "lob", "run_id", "start_time", "end_time", "duration"]:
        if c not in df.columns:
            df[c] = None

    # Optional: standardize lob to string so groupby is clean
    df["lob"] = df["lob"].astype(str)

    return df

summary_df = build_summary_df_from_log(log_data)
display(summary_df)


# ------------- 2) Aggregate per (uw_req_id, scenario_id, lob) and overall -------------

def build_aggregates(summary_df: pd.DataFrame):
    if summary_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Per-combo aggregation
    group_cols = ["uw_req_id", "scenario_id", "lob"]
    combo_summary_df = (
        summary_df
        .groupby(group_cols, dropna=False, as_index=False)[["Total_Tests", "Passed", "Failed"]]
        .sum()
        .sort_values(group_cols)
    )

    # Overall per-table across all combos (this is what you show inline)
    overall_summary_df = (
        summary_df
        .groupby(["Table"], as_index=False)[["Total_Tests", "Passed", "Failed"]]
        .sum()
        .sort_values("Failed", ascending=False)
    )

    return combo_summary_df, overall_summary_df

combo_summary_df, overall_summary_all_df = build_aggregates(summary_df)

print("Per-combination summary:")
display(combo_summary_df)

print("Overall summary across all runs:")
display(overall_summary_all_df)
