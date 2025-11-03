# --- Input parameters ---
dbutils.widgets.text("Lob_id", "1")
dbutils.widgets.text("Scenario_id", "")
dbutils.widgets.text("uw_req_id", "")

lob_id = int(dbutils.widgets.get("Lob_id"))
scenario_id = dbutils.widgets.get("Scenario_id").strip()
uw_req_id = dbutils.widgets.get("uw_req_id").strip()

print(f"✅ Parameters -> Lob ID: {lob_id}, Scenario ID: {scenario_id or 'None'}, UW_REQ_ID: {uw_req_id or 'None'}")



///////////////////


# --- Table Configuration ---
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
            "total_claims", "brand_claims", "brand_zbd_claims", "brand_awp",
            "incl_brand_awp", "excl_brand_awp", "brand_revenue",
            "generic_claims", "generic_zbd_claims", "generic_awp",
            "incl_generic_awp", "excl_generic_awp", "generic_revenue",
            "zinc_value"
        ],
        "uuid_columns": ["network_pricing_group_id"],
        "filters": ""
    },
    # Add more tables here as needed...
}




//////////////////////



def compare_tables_from_config(config: dict, scenario_id: str = None, lob_id: int = None, uw_req_id: str = None):
    """
    MySQL vs StarRocks table comparison.
    Dynamically supports scenario_id and/or uw_req_id filters.
    Generates unified result:
        <metric>_mysql | <metric>_starrocks | <metric>_Result
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

        # --- Dynamic WHERE condition logic ---
        where_conditions_mysql = []
        where_conditions_starrocks = []

        if scenario_id:
            where_conditions_mysql.append(f"p.scenario_id = uuid_to_bin(lower('{scenario_id}'))")
            where_conditions_starrocks.append(f"p.scenario_id = upper('{scenario_id}')")

        if uw_req_id:
            where_conditions_mysql.append(f"p.underwriter_request_id = uuid_to_bin(lower('{uw_req_id}'))")
            where_conditions_starrocks.append(f"p.underwriter_request_id = upper('{uw_req_id}')")

        if not where_conditions_mysql:
            raise ValueError("Either scenario_id or uw_req_id must be provided.")

        where_clause_mysql = " AND ".join(where_conditions_mysql)
        where_clause_starrocks = " AND ".join(where_conditions_starrocks)

        # --- Build SQL queries ---
        cols_expr = ", ".join([f"round(sum(p.{col}), 0) as {col}" for col in compare_cols])
        group_cols = ", ".join(key_cols)

        mysql_query = f"""
            SELECT {group_cols}, {cols_expr}
            FROM {db_mysql}.{mysql_table} p
            WHERE {where_clause_mysql}
              AND p.lob_id = {lob_id} {filters}
            GROUP BY {group_cols}
            ORDER BY {group_cols}
        """

        starrocks_query = f"""
            SELECT {group_cols}, {cols_expr}
            FROM {db_starrocks}.{starrocks_table} p
            WHERE {where_clause_starrocks}
              AND p.lob_id = {lob_id} {filters}
            GROUP BY {group_cols}
            ORDER BY {group_cols}
        """

        # --- Execute queries ---
        mysql_df = mysqlConnection(db_mysql, mysql_query)
        starrocks_df = starrocksConnection(db_starrocks, starrocks_query)

        mysql_pd = mysql_df.toPandas()
        starrocks_pd = starrocks_df.toPandas()

        # --- Convert MySQL UUIDs if needed ---
        if uuid_cols:
            for col in uuid_cols:
                if col in mysql_pd.columns:
                    mysql_pd[col] = mysql_pd[col].apply(
                        lambda x: binascii.hexlify(x).decode("utf-8") if isinstance(x, (bytes, bytearray)) else x
                    )
                if col in starrocks_pd.columns:
                    starrocks_pd[col] = starrocks_pd[col].astype(str)

        # --- Normalize key columns ---
        for col in key_cols:
            if col in mysql_pd.columns:
                mysql_pd[col] = mysql_pd[col].astype(str).str.lower().str.strip()
            if col in starrocks_pd.columns:
                starrocks_pd[col] = starrocks_pd[col].astype(str).str.lower().str.strip()

        # --- Key diagnostics ---
        mysql_keys = set(tuple(x) for x in mysql_pd[key_cols].dropna().values.tolist())
        starrocks_keys = set(tuple(x) for x in starrocks_pd[key_cols].dropna().values.tolist())

        only_mysql = mysql_keys - starrocks_keys
        only_starrocks = starrocks_keys - mysql_keys

        print(f"🔹 MySQL unique keys: {len(mysql_keys)}")
        print(f"🔹 StarRocks unique keys: {len(starrocks_keys)}")
        print(f"⚠️ Keys only in MySQL: {len(only_mysql)} | Keys only in StarRocks: {len(only_starrocks)}")

        if only_mysql:
            print("➡️ Example key only in MySQL:", list(only_mysql)[:2])
        if only_starrocks:
            print("➡️ Example key only in StarRocks:", list(only_starrocks)[:2])

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

        # --- Reorder columns: MySQL → StarRocks → Result ---
        ordered_cols = []
        ordered_cols.extend(key_cols)
        for col in compare_cols:
            ordered_cols.extend([f"{col}_mysql", f"{col}_starrocks", f"{col}_Result"])
        ordered_cols.append("table_name")

        merged = merged[ordered_cols]
        unified_results.append(merged)

        print(f"✅ Completed comparison for: {table_name}")

    # --- Combine all tables ---
    unified_df = pd.concat(unified_results, ignore_index=True)

    print("\n📊 Unified comparison result across all tables:")
    display(unified_df)

    return unified_df


# --- Run comparison ---
final_results_df = compare_tables_from_config(
    config=table_config,
    scenario_id=scenario_id if scenario_id else None,
    lob_id=lob_id,
    uw_req_id=uw_req_id if uw_req_id else None
)
