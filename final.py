

# --- Imports ---
import pandas as pd
import numpy as np
import os
from datetime import datetime

# --- Widgets for Runtime Inputs ---
dbutils.widgets.text("Scenario_id", "")
dbutils.widgets.text("Lob_id", "")

scenario_id = dbutils.widgets.get("Scenario_id").strip().lower()
lob_id = int(dbutils.widgets.get("Lob_id").strip())

print(f"📘 Scenario ID: {scenario_id}")
print(f"📗 LOB ID: {lob_id}")

# --- Load Shared Utilities (MySQL, Starrocks connections, etc.) ---
%run "/Workspace/Shared/QA Test Automation/Library/mysqlConnection"
%run "/Workspace/Shared/QA Test Automation/Library/Utilities"
%run "/Workspace/Shared/QA Test Automation/Star Rocks Migration/Validation_Helper"



##################################

    # Table-specific metadata configuration
table_config = {
    "pbm_sensitivities": {
        "mysql_table": "pbm_sensitivities",
        "starrocks_table": "pbm_sensitivities",
        "key_columns": [
            "proj_year", "channel_group_id",
            "pharmacy_capped_noncapped_id", "network_pricing_group_id"
        ],
        "compare_columns": [
            "total_claims", "brand_claims", "brand_awp", "generic_awp"
        ]
    },
    "rebate_summary": {
        "mysql_table": "rebate_summary",
        "starrocks_table": "rebate_summary",
        "key_columns": [
            "proj_year", "rebate_group_id", "channel_group_id"
        ],
        "compare_columns": [
            "rebate_amount", "rebate_percentage"
        ],
        "filters": "AND p.is_active = 1"
    }
}




#################################


def compare_tables_from_config(config: dict, scenario_id: str, lob_id: int):
    """
    Generic MySQL vs StarRocks table comparison.
    Displays results for each table within Databricks.
    """

    all_results = []

    for table_name, cfg in config.items():
        print(f"\n🔍 Comparing table: {table_name}")

        # Extract configuration
        mysql_table = cfg["mysql_table"]
        starrocks_table = cfg["starrocks_table"]
        db_mysql = cfg.get("db_mysql", "comp_engine_microservice_output")
        db_starrocks = cfg.get("db_starrocks", "comp_engine_microservice_output_qa")
        key_cols = cfg["key_columns"]
        compare_cols = cfg["compare_columns"]
        filters = cfg.get("filters", "")

        # --- Build dynamic query ---
        cols_expr = ", ".join([f"round(sum(p.{col}),0) as {col}" for col in compare_cols])
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

        # --- Fetch data ---
        mysql_df = mysqlConnection(db_mysql, mysql_query)
        starrocks_df = starrocksConnection(db_starrocks, starrocks_query)

        mysql_pd = mysql_df.toPandas()
        starrocks_pd = starrocks_df.toPandas()

        # --- Merge and Compare ---
        merged = mysql_pd.merge(
            starrocks_pd,
            on=key_cols,
            how="outer",
            suffixes=("_mysql", "_starrocks"),
            indicator=True
        )

        def compare_row(row, col):
            if row["_merge"] == "both":
                return "Match" if row[f"{col}_mysql"] == row[f"{col}_starrocks"] else "Mismatch"
            elif row["_merge"] == "left_only":
                return "Missing in StarRocks"
            else:
                return "Missing in MySQL"

        for col in compare_cols:
            merged[f"{col}_Result"] = merged.apply(lambda r: compare_row(r, col), axis=1)

        result_cols = key_cols + [f"{col}_Result" for col in compare_cols]
        result_df = merged[result_cols]
        result_df["table_name"] = table_name

        all_results.append(result_df)
        display(result_df)

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



    
