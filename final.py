def compare_tables_from_config(config: dict, scenario_id: str, lob_id: int):
    """
    Generic MySQL vs StarRocks table comparison.
    Handles duplicate rows and order differences by pre-aggregating on key columns.
    Displays MySQL value, StarRocks value, and mismatch details.
    """

    all_results = []

    for table_name, cfg in config.items():
        print(f"\n🔍 Comparing table: {table_name}")

        # --- Extract config ---
        mysql_table = cfg["mysql_table"]
        starrocks_table = cfg["starrocks_table"]
        db_mysql = cfg.get("db_mysql", "comp_engine_microservice_output")
        db_starrocks = cfg.get("db_starrocks", "comp_engine_microservice_output_qa")
        key_cols = cfg["key_columns"]
        compare_cols = cfg["compare_columns"]
        filters = cfg.get("filters", "")

        # --- Build dynamic SQL ---
        cols_expr = ", ".join([f"p.{col}" for col in compare_cols])
        group_cols = ", ".join(key_cols)

        mysql_query = f"""
            SELECT {group_cols}, {cols_expr}
            FROM {db_mysql}.{mysql_table} p
            WHERE p.scenario_id = uuid_to_bin(lower('{scenario_id}'))
            AND p.lob_id = {lob_id} {filters}
        """

        starrocks_query = f"""
            SELECT {group_cols}, {cols_expr}
            FROM {db_starrocks}.{starrocks_table} p
            WHERE p.scenario_id = upper('{scenario_id}')
            AND p.lob_id = {lob_id} {filters}
        """

        # --- Fetch data ---
        mysql_df = mysqlConnection(db_mysql, mysql_query)
        starrocks_df = starrocksConnection(db_starrocks, starrocks_query)

        mysql_pd = mysql_df.toPandas()
        starrocks_pd = starrocks_df.toPandas()

        # --- Pre-aggregate (duplicate-insensitive) ---
        mysql_agg = mysql_pd.groupby(key_cols, dropna=False)[compare_cols].sum().reset_index()
        starrocks_agg = starrocks_pd.groupby(key_cols, dropna=False)[compare_cols].sum().reset_index()

        # --- Merge on key columns ---
        merged = mysql_agg.merge(
            starrocks_agg,
            on=key_cols,
            how="outer",
            suffixes=("_mysql", "_starrocks"),
            indicator=True
        )

        # --- Enhanced comparison ---
        def compare_row(row, col):
            if row["_merge"] == "both":
                mysql_val = row.get(f"{col}_mysql")
                starrocks_val = row.get(f"{col}_starrocks")

                if pd.isna(mysql_val) and pd.isna(starrocks_val):
                    return "Match"
                elif mysql_val == starrocks_val:
                    return "Match"
                else:
                    return f"Mismatch → MySQL: {mysql_val}, StarRocks: {starrocks_val}"

            elif row["_merge"] == "left_only":
                return "Missing in StarRocks"
            else:
                return "Missing in MySQL"

        for col in compare_cols:
            merged[f"{col}_Result"] = merged.apply(lambda r: compare_row(r, col), axis=1)

        # --- Build visible result ---
        visible_cols = (
            key_cols
            + [f"{col}_mysql" for col in compare_cols]
            + [f"{col}_starrocks" for col in compare_cols]
            + [f"{col}_Result" for col in compare_cols]
        )

        result_df = merged[visible_cols]
        result_df["table_name"] = table_name

        all_results.append(result_df)
        print(f"✅ Completed comparison for: {table_name}")
        display(result_df)

    # --- Combined summary across all tables ---
    combined_df = pd.concat(all_results, ignore_index=True)
    print("\n📊 Combined summary across all tables:")
    display(combined_df)

    return combined_df


# --- Run comparison ---
final_results_df = compare_tables_from_config(
    config=table_config,
    scenario_id=scenario_id,
    lob_id=lob_id
)
