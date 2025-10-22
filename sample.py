# Databricks notebook cell

import os
import shutil
from pyspark.dbutils import DBUtils

dbutils = DBUtils(spark)

def get_download_link(file_path: str):
    """
    Generate a clickable Databricks download link for a file.
    Works for both DBFS and /Workspace paths.
    """

    file_name = os.path.basename(file_path)
    workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
    dbfs_target = f"/dbfs/FileStore/{file_name}"
    dbfs_uri = f"dbfs:/FileStore/{file_name}"

    # --- CASE 1: File already in DBFS/FileStore ---
    if file_path.startswith("dbfs:/FileStore/") or file_path.startswith("/dbfs/FileStore/"):
        download_url = f"https://{workspace_url}/files/{file_name}"
        displayHTML(f'<a href="{download_url}" target="_blank">⬇️ Download {file_name}</a>')
        return download_url

    # --- CASE 2: File in Workspace (copy attempt) ---
    elif file_path.startswith("/Workspace/"):
        try:
            # Try to copy file using dbutils first (if permissions allow)
            print(f"📂 Copying from Workspace → {dbfs_uri}")
            dbutils.fs.cp(file_path, dbfs_uri)
        except Exception as e:
            # Fallback: try Python local /dbfs copy (works in single-user clusters)
            local_target = f"/dbfs/FileStore/{file_name}"
            if os.path.exists(file_path):
                shutil.copy(file_path, local_target)
                print(f"✅ Copied via local path: {file_path} → {local_target}")
            else:
                raise FileNotFoundError(
                    f"❌ Cannot access {file_path}. "
                    "Workspace files are not directly readable by clusters. "
                    "Please download it locally and upload to FileStore via UI: "
                    "Data → DBFS → FileStore → Upload File."
                )

    # --- CASE 3: File in other DBFS path (like dbfs:/mnt/...) ---
    else:
        print(f"📂 Copying from DBFS → {dbfs_uri}")
        dbutils.fs.cp(file_path, dbfs_uri)

    # --- Generate Download URL ---
    download_url = f"https://{workspace_url}/files/{file_name}"
    displayHTML(f'<a href="{download_url}" target="_blank">⬇️ Download {file_name}</a>')
    return download_url


# 🧠 Example usage — replace below with your file path:
get_download_link("/Workspace/Shared/QA Test Automation/Star Rocks Migration/Validate_Table_Output/Latest-Sai/OCT-22/Input_235A0FD3600412DA9E8AB2BF62EDDCCD_QA_2025-10-22_07-17-37.xlsx")
