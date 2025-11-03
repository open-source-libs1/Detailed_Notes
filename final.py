def compare_tables_from_config(config: dict, scenario_id: str, lob_id: int):
    """
    MySQL vs StarRocks table comparison with UUID hex conversion and key normalization.
    Performs SQL-side aggregation (GROUP BY + ORDER BY) for consistency.
    Produces a unified DataFrame where each metric appears as:
        <metric>_mysql | <metric>_starrocks | <metric>_Result
    Also prints quick key-alignment diagnostics.
    """

    import binascii
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
        uuid_cols = cfg.get("uuid_columns", [])
        filters = cfg.get("filters", "")

        # --- Build SQL queries with aggregation ---
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

        # --- Execute queries and convert to pandas ---
        mysql_df = mysqlConnection(db_mysql, mysql_query)
        starrocks_df = starrocksConnection(db_starrocks, starrocks_query)

        mysql_pd = mysql_df.toPandas()
        starrocks_pd = starrocks_df.toPandas()

        # --- Convert binary UUIDs and normalize keys ---
        if uuid_cols:
            for col in uuid_cols:
                if col in mysql_pd.columns:
                    mysql_pd[col] = mysql_pd[col].apply(
                        lambda x: binascii.hexlify(x).decode("utf-8") if isinstance(x, (bytes, bytearray)) else x
                    )
                if col in starrocks_pd.columns:
                    starrocks_pd[col] = starrocks_pd[col].astype(str)

        # Normalize all key columns (lowercase, trim, stringify)
        for col in key_cols:
            if col in mysql_pd.columns:
                mysql_pd[col] = mysql_pd[col].astype(str).str.lower().str.strip()
            if col in starrocks_pd.columns:
                starrocks_pd[col] = starrocks_pd[col].astype(str).str.lower().str.strip()

        # --- Quick key alignment diagnostics ---
        mysql_keys = set(tuple(x) for x in mysql_pd[key_cols].dropna().values.tolist())
        starrocks_keys = set(tuple(x) for x in starrocks_pd[key_cols].dropna().values.tolist())
        only_mysql = mysql_keys - starrocks_keys
        only_starrocks = starrocks_keys - mysql_keys

        print(f"🔹 MySQL unique keys: {len(mysql_keys)}")
        print(f"🔹 StarRocks unique keys: {len(starrocks_keys)}")
        print(f"⚠️ Keys only in MySQL: {len(only_mysql)}  |  Keys only in StarRocks: {len(only_starrocks)}")

        # --- Merge datasets on normalized keys ---
        merged = mysql_pd.merge(
            starrocks_pd,
            on=key_cols,
            how="outer",
            suffixes=("_mysql", "_starrocks"),
            indicator=True
        )

        # --- Compare each metric and build Result columns ---
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

        # --- Interleave columns (MySQL | StarRocks | Result) ---
        ordered_cols = []
        ordered_cols.extend(key_cols)
        for col in compare_cols:
            ordered_cols.extend([f"{col}_mysql", f"{col}_starrocks", f"{col}_Result"])
        ordered_cols.append("table_name")

        merged = merged[ordered_cols]
        unified_results.append(merged)

        print(f"✅ Completed comparison for: {table_name}")

    # --- Combine all tables into one DataFrame ---
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
