

def compare_tables_from_config(config: dict, scenario_id: str, lob_id: int):
    """
    Generic MySQL vs StarRocks comparison across multiple tables.
    Displays a single unified dataframe combining MySQL, StarRocks, and Result columns.
    Handles duplicate keys and order differences by pre-aggregating.
    """

    unified_results = []

    for table_name, cfg in config.items():
        print(f"\n🔍 Comparing table: {table_name}")

        mysql_table = cfg["mysql_table"]
        starrocks_table = cfg["starrocks_table"]
        db_mysql = cfg.get("db_mysql", "comp_engine_microservice_output")
        db_starrocks = cfg.get("db_starrocks", "comp_engine_microservice_output_qa")
        key_cols = cfg["key_columns"]
        compare_cols = cfg["compare_columns"]
        filters = cfg.get("filters", "")

        # --- Build dynamic SQL ---
        cols_expr = ", ".join([f"p.{col}" for col in compare_cols])
        key_expr = ", ".join(key_cols)

        mysql_query = f"""
            SELECT {key_expr}, {cols_expr}
            FROM {db_mysql}.{mysql_table} p
            WHERE p.scenario_id = uuid_to_bin(lower('{scenario_id}'))
            AND p.lob_id = {lob_id} {filters}
        """

        starrocks_query = f"""
            SELECT {key_expr}, {cols_expr}
            FROM {db_starrocks}.{starrocks_table} p
            WHERE p.scenario_id = upper('{scenario_id}')
            AND p.lob_id = {lob_id} {filters}
        """

        # --- Execute queries ---
        mysql_df = mysqlConnection(db_mysql, mysql_query)
        starrocks_df = starrocksConnection(db_starrocks, starrocks_query)

        mysql_pd = mysql_df.toPandas()
        starrocks_pd = starrocks_df.toPandas()

        # --- Pre-aggregate (handle duplicates / order issues) ---
        mysql_agg = mysql_pd.groupby(key_cols, dropna=False)[compare_cols].sum().reset_index()
        starrocks_agg = starrocks_pd.groupby(key_cols, dropna=False)[compare_cols].sum().reset_index()

        # --- Merge MySQL & StarRocks ---
        merged = mysql_agg.merge(
            starrocks_agg,
            on=key_cols,
            how="outer",
            suffixes=("_mysql", "_starrocks"),
            indicator=True
        )

        # --- Compare & Build Result Columns ---
        for col in compare_cols:
            def compare_row(row):
                mysql_val = row.get(f"{col}_mysql")
                starrocks_val = row.get(f"{col}_starrocks")

                # handle missing cases
                if row["_merge"] == "left_only":
                    return "Missing in StarRocks"
                elif row["_merge"] == "right_only":
                    return "Missing in MySQL"

                # handle value comparison
                if pd.isna(mysql_val) and pd.isna(starrocks_val):
                    return "Match"
                elif mysql_val == starrocks_val:
                    return "Match"
                else:
                    return f"Mismatch → MySQL: {mysql_val}, StarRocks: {starrocks_val}"

            merged[f"{col}_Result"] = merged.apply(compare_row, axis=1)

        merged["table_name"] = table_name
        unified_results.append(merged)

        print(f"✅ Completed comparison for: {table_name}")

    # --- Combine all tables into one unified DataFrame ---
    unified_df = pd.concat(unified_results, ignore_index=True)

    # --- Drop merge indicator column ---
    if "_merge" in unified_df.columns:
        unified_df.drop(columns=["_merge"], inplace=True)

    print("\n📊 Unified comparison result across all tables:")
    display(unified_df)

    return unified_df


# --- Run comparison ---
final_results_df = compare_tables_from_config(
    config=table_config,
    scenario_id=scenario_id,
    lob_id=lob_id
)
