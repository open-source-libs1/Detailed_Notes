reference_table_result_dfs = {}
summary_table_header = f"{environment}_Table"
summary_results = {summary_table_header: [], "Result": []}

# Columns to compare
key_columns = ["TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"]

# Columns to ignore for comparison
ignore_columns = ["created_at", "updated_at", "createdAt", "updatedAt"]

for table_name in reference_tables:
    print(table_name)

    # 1️⃣ Get MySQL & SR schema dataframes
    mysql_df = query_dfs[table_name][mysql_key]
    sr_df = query_dfs[table_name][compared_key]

    # 2️⃣ Drop ignored columns (if present)
    mysql_df = mysql_df[[c for c in mysql_df.columns if c not in ignore_columns]]
    sr_df    = sr_df[[c for c in sr_df.columns if c not in ignore_columns]]

    # 3️⃣ Perform comparison (no change to function call)
    pass_fail_df = compare_pass_fail_df2(
        mysql_df,
        sr_df,
        key_columns,
        mysql_key,
        compared_key,
        columns_to_keep,
        join_type="outer"
    )

    reference_table_result_dfs[table_name] = pass_fail_df

    summary_results[summary_table_header].append(table_name)
    summary_result = "Pass" if (pass_fail_df["Result"] == "Pass").all() else "Fail"
    summary_results["Result"].append(summary_result)
