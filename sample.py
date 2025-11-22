# columns (schema rows) to ignore but still show as Pass in output
ignore_columns = {"created_at", "updated_at", "createdAt", "updatedAt"}

reference_table_result_dfs = {}
summary_table_header = f"{environment}_Table"
summary_results = {summary_table_header: [], "Result": []}

key_columns = ["TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"]

for table_name in reference_tables:
    print(f"\n=== Comparing table: {table_name} ===")

    mysql_df = query_dfs[table_name][mysql_key]
    sr_df    = query_dfs[table_name][compared_key]

    # Debug: initial sizes
    print(f"[DEBUG] mysql rows before ignore: {len(mysql_df)}")
    print(f"[DEBUG] sr rows before ignore:    {len(sr_df)}")

    # Find ignored rows in each side (by COLUMN_NAME)
    mysql_ignored = mysql_df[mysql_df["COLUMN_NAME"].isin(ignore_columns)]
    sr_ignored    = sr_df[sr_df["COLUMN_NAME"].isin(ignore_columns)]

    print(f"[DEBUG] ignored in mysql: {mysql_ignored['COLUMN_NAME'].tolist()}")
    print(f"[DEBUG] ignored in sr:    {sr_ignored['COLUMN_NAME'].tolist()}")

    # Filter them out for comparison
    mysql_cmp = mysql_df[~mysql_df["COLUMN_NAME"].isin(ignore_columns)]
    sr_cmp    = sr_df[~sr_df["COLUMN_NAME"].isin(ignore_columns)]

    print(f"[DEBUG] mysql rows after ignore: {len(mysql_cmp)}")
    print(f"[DEBUG] sr rows after ignore:    {len(sr_cmp)}")

    # Compare (NO CHANGE to function call)
    pass_fail_df = compare_pass_fail_df2(
        mysql_cmp,
        sr_cmp,
        key_columns,
        mysql_key,
        compared_key,
        columns_to_keep,
        join_type="outer"
    )

    # Make ignored rows show up as Pass in result
    ignored_union = pd.concat([mysql_ignored, sr_ignored], ignore_index=True).drop_duplicates(
        subset=["TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"]
    )
    if not ignored_union.empty:
        ignored_union = ignored_union[key_columns].copy()
        ignored_union["Result"] = "Pass"
        pass_fail_df = pd.concat([pass_fail_df, ignored_union], ignore_index=True)

    # Optional debug: final result counts
    print(f"[DEBUG] final result rows (incl ignored): {len(pass_fail_df)}")
    print(f"[DEBUG] final pass count: {(pass_fail_df['Result']=='Pass').sum()}, "
          f"fail count: {(pass_fail_df['Result']=='Fail').sum()}")

    reference_table_result_dfs[table_name] = pass_fail_df
    summary_results[summary_table_header].append(table_name)
    summary_results["Result"].append("Pass" if (pass_fail_df["Result"] == "Pass").all() else "Fail")
