import pandas as pd
import re
from datetime import datetime

# 1) Collect your DFs (Spark + Pandas mixed is OK)
final_result_dfs = {
    "Conventional": rebate_conventional_df,  # Spark DF
    "TC": starrocks_rebate_df,               # Spark DF
    "Comparison": compared_rebate_df,        # Pandas DF
}

# 2) Target "Workspace location" on DBFS
export_dir_dbfs = "dbfs:/Workspace/Shared/QA Test Automation/True Cost/Rebate_Validation_Output"
dbutils.fs.mkdirs(export_dir_dbfs)

export_file_name = f"Rebate_Conv_vs_TC_{uw_req_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

# Pandas needs a local-style path -> use the /dbfs mirror of DBFS
export_dir_local = "/dbfs/" + export_dir_dbfs.replace("dbfs:/", "")
output_path_local = f"{export_dir_local}/{export_file_name}"

def _sheet(name: str) -> str:
    name = re.sub(r'[\[\]\:\*\?\/\\]', "_", str(name))
    return (name[:31] or "Sheet1")

with pd.ExcelWriter(output_path_local, engine="openpyxl") as writer:
    for sheet_name, df in final_result_dfs.items():
        # Spark -> pandas
        if hasattr(df, "toPandas"):
            df = df.toPandas()
        df.to_excel(writer, sheet_name=_sheet(sheet_name), index=False)

print("✅ Written to:", f"{export_dir_dbfs}/{export_file_name}")
