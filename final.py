def compare_tables_from_config(config: dict, scenario_id: str = None, lob_id: int = None, uw_req_id: str = None, show_queries: bool = True):
    """
    Enhanced MySQL vs StarRocks comparison with:
      - Per-table filter modes (scenario_id / uw_req_id / both)
      - Optional lob_id inclusion
      - Automatic fallback to SELECT * when key_columns list is empty
      - Query printouts for debugging
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
        key_cols = cfg.get("key_columns", [])
        compare_cols = cfg.get("compare_columns", [])
        uuid_cols = cfg.get("uuid_columns", [])
        filters = cfg.get("filters", "")
        mysql_mode = cfg.get("mysql_filter_mode", "both").lower()
        starrocks_mode = cfg.get("starrocks_filter_mode", "both").lower()
        use_lob = cfg.get("use_lob_filter", True)

        # --- WHERE condition builders ---
        def build_conditions(mode, engine):
            conds = []
            if mode in ("scenario_id", "both") and scenario_id:
                conds.append(
                    f"p.scenario_id = {'uuid_to_bin(lower' if engine=='mysql' else 'upper'}('{scenario_id}'){')' if engine=='mysql' else ''}"
                )
            if mode in ("uw_req_id", "both") and uw_req_id:
                conds.append(
                    f"p.underwriter_request_id = {'uuid_to_bin(lower' if engine=='mysql' else 'upper'}('{uw_req_id}'){')' if engine=='mysql' else ''}"
                )
            return " AND ".join(conds)

        mysql_where = build_conditions(mysql_mode, "mysql")
        starrocks_where = build_conditions(starrocks_mode, "starrocks")

        if not mysql_where and not starrocks_where:
            raise ValueError(f"⚠️ Table {table_name}: missing valid filter fields.")

        # --- LOB filter logic ---
        lob_clause = f"AND p.lob_id = {lob_id}" if use_lob and lob_id is not None else ""

        # --- Build SQL queries ---
        if key_cols:  # ✅ Aggregated mode (grouped)
            cols_expr = ", ".join([f"round(sum(p.{col}), 0) as {col}" for col in compare_cols])
            group_cols = ", ".join(key_cols)

            mysql_query = f"""
                SELECT {group_cols}, {cols_expr}
                FROM {db_mysql}.{mysql_table} p
                WHERE {mysql_where}
                  {lob_clause} {filters}
                GROUP BY {group_cols}
                ORDER BY {group_cols}
            """

            starrocks_query = f"""
                SELECT {group_cols}, {cols_expr}
                FROM {db_starrocks}.{starrocks_table} p
                WHERE {starrocks_where}
                  {lob_clause} {filters}
                GROUP BY {group_cols}
                ORDER BY {group_cols}
            """
        else:  # ✅ Detail mode (no grouping)
            print(f"ℹ️ Table {table_name} has no key_columns defined — using SELECT * mode.")
            mysql_query = f"""
                SELECT *
                FROM {db_mysql}.{mysql_table} p
                WHERE {mysql_where}
                  {lob_clause} {filters}
            """

            starrocks_query = f"""
                SELECT *
                FROM {db_starrocks}.{starrocks_table} p
                WHERE {starrocks_where}
                  {lob_clause} {filters}
            """

        # --- Print generated queries ---
        if show_queries:
            print("\n🟦 MySQL Query:")
            print(mysql_query)
            print("\n🟩 StarRocks Query:")
            print(starrocks_query)
            print("-" * 80)

        # --- Execute queries ---
        try:
            mysql_df = mysqlConnection(db_mysql, mysql_query)
        except Exception as e:
            print(f"❌ MySQL query failed for {table_name}: {e}")
            continue

        try:
            starrocks_df = starrocksConnection(db_starrocks, starrocks_query)
        except Exception as e:
            print(f"❌ StarRocks query failed for {table_name}: {e}")
            continue

        mysql_pd = mysql_df.toPandas()
        starrocks_pd = starrocks_df.toPandas()

        # --- Convert UUIDs and normalize keys ---
        if uuid_cols:
            for col in uuid_cols:
                if col in mysql_pd.columns:
                    mysql_pd[col] = mysql_pd[col].apply(
                        lambda x: binascii.hexlify(x).decode("utf-8") if isinstance(x, (bytes, bytearray)) else x
                    )
                if col in starrocks_pd.columns:
                    starrocks_pd[col] = starrocks_pd[col].astype(str)

        if key_cols:
            for col in key_cols:
                if col in mysql_pd.columns:
                    mysql_pd[col] = mysql_pd[col].astype(str).str.lower().str.strip()
                if col in starrocks_pd.columns:
                    starrocks_pd[col] = starrocks_pd[col].astype(str).str.lower().str.strip()

        # --- Key diagnostics ---
        mysql_keys = len(mysql_pd) if not key_cols else len(mysql_pd[key_cols].dropna())
        starrocks_keys = len(starrocks_pd) if not key_cols else len(starrocks_pd[key_cols].dropna())
        print(f"🔹 MySQL rows: {mysql_keys} | StarRocks rows: {starrocks_keys}")

        # --- Merge datasets ---
        if key_cols:
            merged = mysql_pd.merge(
                starrocks_pd,
                on=key_cols,
                how="outer",
                suffixes=("_mysql", "_starrocks"),
                indicator=True
            )
        else:
            # If no keys, align by index for comparison
            merged = mysql_pd.merge(
                starrocks_pd,
                left_index=True,
                right_index=True,
                how="outer",
                suffixes=("_mysql", "_starrocks"),
                indicator=True
            )

        # --- Compare each metric ---
        compare_targets = compare_cols if compare_cols else [
            c for c in mysql_pd.columns if c in starrocks_pd.columns
        ]
        for col in compare_targets:
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

        # --- Column order ---
        ordered_cols = []
        if key_cols:
            ordered_cols.extend(key_cols)
        for col in compare_targets:
            ordered_cols.extend([f"{col}_mysql", f"{col}_starrocks", f"{col}_Result"])
        ordered_cols.append("table_name")

        merged = merged[[c for c in ordered_cols if c in merged.columns]]
        unified_results.append(merged)

        print(f"✅ Completed comparison for: {table_name}")

    unified_df = pd.concat(unified_results, ignore_index=True)
    print("\n📊 Unified comparison result across all tables:")
    display(unified_df)
    return unified_df


# --- Run comparison ---
final_results_df = compare_tables_from_config(
    config=table_config,
    scenario_id=scenario_id if scenario_id else None,
    lob_id=lob_id,
    uw_req_id=uw_req_id if uw_req_id else None,
    show_queries=True
)



///////////////////////


"pnl_claim_detail": {
    "mysql_table": "pnl_claim_detail",
    "starrocks_table": "pnl_claim_detail_tc",
    "key_columns": [],  # 👈 triggers SELECT *
    "compare_columns": [],  # auto infer overlap
    "uuid_columns": [],
    "filters": "",
    "mysql_filter_mode": "uw_req_id",
    "starrocks_filter_mode": "uw_req_id",
    "use_lob_filter": False
}
