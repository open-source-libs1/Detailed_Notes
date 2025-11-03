


table_config = {
    "pbm_sensitivities": {
        "mysql_table": "pbm_sensitivities",
        "starrocks_table": "pbm_sensitivities",
        "key_columns": [
            "proj_year",
            "channel_group_id",
            "pharmacy_capped_noncapped_id",
            "network_pricing_group_id"
        ],
        "compare_columns": [
            "total_claims", "brand_claims", "brand_awp", "generic_awp"
        ],
        "uuid_columns": ["network_pricing_group_id"]
    }
}



################


def compare_tables_from_config(config: dict, scenario_id: str, lob_id: int):
    """
    MySQL vs StarRocks table comparison.
    Fixes key mismatches by converting MySQL UUID columns.
    Performs SQL aggregation and displays unified comparison:
        <metric>_mysql | <metric>_starrocks | <metric>_Result
    """

    unified_results = []

    for table_name, cfg in config.items():
        print(f"\n🔍 Comparing table: {table_name}")

        # --- Extract config ---
        mysql_table = cfg["mysql_table"]
        starrocks_table = cfg["starrocks_table"]
        db_mysql = cfg.get("db_mysql", "comp_engine_microservice_output")
        db_starrocks = cfg.get("db_starrocks", "comp_engine_microservice_output_qa")
        key_cols = cfg["key_columns"]
        compare_cols = cfg["compare_columns"]
        uuid_cols = cfg.get("uuid_columns", [])   # ✅ optional UUID conversion
        filters = cfg.get("filters", "")

        # --- Build SQL with aggregation ---
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

        # --- Convert MySQL binary UUID columns if required ---
        if uuid_cols:
            for col in uuid_cols:
                if col in mysql_pd.columns:
                    mysql_pd[col] = mysql_pd[col].apply(
                        lambda x: x.decode("utf-8") if isinstance(x, (bytes, bytearray)) else x
                    )

        # --- Merge both datasets ---
        merged = mysql_pd.merge(
            starrocks_pd,
            on=key_cols,
            how="outer",
            suffixes=("_mysql", "_starrocks"),
            indicator=True
        )

        # --- Compare each metric ---
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

        # --- Build interleaved column order ---
        ordered_cols = []
        ordered_cols.extend(key_cols)
        for col in compare_cols:
            ordered_cols.extend([f"{col}_mysql", f"{col}_starrocks", f"{col}_Result"])
        ordered_cols.append("table_name")

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
