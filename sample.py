
import os
from pyspark.dbutils import DBUtils

dbutils = DBUtils(spark)

def get_download_link(workspace_file_path: str):
    """
    Copy a file from Workspace or local path into DBFS FileStore
    and return a downloadable Databricks link.
    """

    # Extract file name
    file_name = os.path.basename(workspace_file_path)

    # Define DBFS target path
    dbfs_target = f"dbfs:/FileStore/{file_name}"

    print(f"📂 Copying {workspace_file_path} → {dbfs_target}")

    # Copy file to FileStore
    # Works only if you have permission to read the Workspace file
    dbutils.fs.cp(workspace_file_path, dbfs_target, recurse=False)

    # Build HTTPS link
    workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
    download_url = f"https://{workspace_url}/files/{file_name}"

    # Show clickable HTML link
    displayHTML(f'<a href="{download_url}" target="_blank">⬇️ Download {file_name}</a>')

    return download_url
