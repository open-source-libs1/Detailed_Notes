

def compare_tables_from_config(config: dict, scenario_id: str, lob_id: int):
    """
    Generic MySQL vs StarRocks table comparison.
    Performs SQL-side aggregation (GROUP BY + ORDER BY) for consistency.
    Produces a single unified DataFrame where each metric is shown as:
        <metric>_mysql | <metric>_starrocks | <metric>_Result
    """

    unified_results = []

    for table_name, cfg in config.items():
        print(f"\n🔍 Comparing table: {table_name}")

        # --- Extract configuration ---
        mysql_table = cfg["mysql_table"]
        starrocks_table = cfg["starrocks_table"]
        db_mysql = cfg.get("db_mysql", "comp_engine_microservice_output")
        db_starrocks = cfg.get("db_starrocks", "comp_engine_microservice_output_qa")
        key_cols = cfg["key_columns"]
        compare_cols = cfg["compare_columns"]
        filters = cfg.get("filters", "")

        # --- Build SQL with aggregation and deterministic order ---
        cols_expr = ", ".join([f"round(sum(p.{col}), 0) as {col}" for col in compare_cols])
        group_cols = ", ".join(key_cols)

        mysql_query = f"""
            SELECT {group_cols}, {cols_expr}
            FROM {db_mysql}.{mysql_table} p
            WHERE p.scenario_id = uuid_to_bin(lower('{scenario_id}'))
              AND p.lob_id = {lob_id} {filters}
            GROUP BY {group_cols}
            ORDER BY {group_cols}
        """

        starrocks_query = f"""
            SELECT {group_cols}, {cols_expr}
            FROM {db_starrocks}.{starrocks_table} p
            WHERE p.scenario_id = upper('{scenario_id}')
              AND p.lob_id = {lob_id} {filters}
            GROUP BY {group_cols}
            ORDER BY {group_cols}
        """

        # --- Execute queries ---
        mysql_df = mysqlConnection(db_mysql, mysql_query)
        starrocks_df = starrocksConnection(db_starrocks, starrocks_query)

        mysql_pd = mysql_df.toPandas()
        starrocks_pd = starrocks_df.toPandas()

        # --- No further aggregation; already grouped by SQL ---
        mysql_agg = mysql_pd
        starrocks_agg = starrocks_pd

        # --- Merge MySQL & StarRocks data ---
        merged = mysql_agg.merge(
            starrocks_agg,
            on=key_cols,
            how="outer",
            suffixes=("_mysql", "_starrocks"),
            indicator=True
        )

        # --- Compare each metric column ---
        for col in compare_cols:
            def compare_row(row):
                mysql_val = row.get(f"{col}_mysql")
                starrocks_val = row.get(f"{col}_starrocks")

                if row["_merge"] == "left_only":
                    return "Missing in StarRocks"
                elif row["_merge"] == "right_only":
                    return "Missing in MySQL"

                if pd.isna(mysql_val) and pd.isna(starrocks_val):
                    return "Match"
                elif mysql_val == starrocks_val:
                    return "Match"
                else:
                    return f"Mismatch → MySQL: {mysql_val}, StarRocks: {starrocks_val}"

            merged[f"{col}_Result"] = merged.apply(compare_row, axis=1)

        merged["table_name"] = table_name

        # --- Build ordered column layout ---
        ordered_cols = []
        ordered_cols.extend(key_cols)  # Start with key columns

        # For each metric: MySQL → StarRocks → Result
        for col in compare_cols:
            ordered_cols.append(f"{col}_mysql")
            ordered_cols.append(f"{col}_starrocks")
            ordered_cols.append(f"{col}_Result")

        ordered_cols.append("table_name")

        # Reorder merged DataFrame
        merged = merged[ordered_cols]

        unified_results.append(merged)
        print(f"✅ Completed comparison for: {table_name}")

    # --- Combine all tables into one unified DataFrame ---
    unified_df = pd.concat(unified_results, ignore_index=True)

    print("\n📊 Unified comparison result across all tables:")
    display(unified_df)

    return unified_df


# --- Run comparison ---
final_results_df = compare_tables_from_config(
    config=table_config,
    scenario_id=scenario_id,
    lob_id=lob_id
)
