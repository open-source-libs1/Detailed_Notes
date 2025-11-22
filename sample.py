pass_fail_df = compare_pass_fail_df2(...)

# --- insert patch here ---
ignore_cols = {"created_at", "updated_at"}
pass_fail_df["COLUMN_NAME_lower"] = pass_fail_df["COLUMN_NAME"].str.lower()
pass_fail_df.loc[
    pass_fail_df["COLUMN_NAME_lower"].isin(ignore_cols), "Result"
] = "Pass"
pass_fail_df.drop(columns=["COLUMN_NAME_lower"], inplace=True)
# ---------------------------

reference_table_result_dfs[table_name] = pass_fail_df
