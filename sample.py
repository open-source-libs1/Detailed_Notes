

# Example if you created a Pandas DataFrame originally
output_path = "/dbfs/FileStore/Input_235A0FD3600412DA9E8AB2BF62EDDCCD_QA_2025-10-22_07-17-37.xlsx"
my_dataframe.to_excel(output_path, index=False)

# Then create a link
from pyspark.dbutils import DBUtils
dbutils = DBUtils(spark)

workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
file_name = output_path.split("/")[-1]
download_url = f"https://{workspace_url}/files/{file_name}"
displayHTML(f'<a href="{download_url}" target="_blank">⬇️ Download {file_name}</a>')




#######################


import requests
import json

# --- Configuration ---
workspace_file_path = "/Workspace/Shared/QA Test Automation/Star Rocks Migration/Validate_Table_Output/Latest-Sai/OCT-22/Input_235A0FD3600412DA9E8AB2BF62EDDCCD_QA_2025-10-22_07-17-37.xlsx"
local_save_path = "/dbfs/FileStore/Input_235A0FD3600412DA9E8AB2BF62EDDCCD_QA_2025-10-22_07-17-37.xlsx"

# Get your current Databricks token and URL
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
workspace_url = spark.conf.get("spark.databricks.workspaceUrl")

# --- API Request ---
headers = {"Authorization": f"Bearer {token}"}
export_url = f"https://{workspace_url}/api/2.0/workspace/export"

params = {"path": workspace_file_path, "format": "SOURCE"}
response = requests.get(export_url, headers=headers, params=params)

if response.status_code == 200:
    with open(local_save_path, "wb") as f:
        f.write(response.content)
    print(f"✅ Exported to: {local_save_path}")
else:
    print(f"❌ Export failed: {response.status_code} - {response.text}")


////


file_name = "Input_235A0FD3600412DA9E8AB2BF62EDDCCD_QA_2025-10-22_07-17-37.xlsx"
workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
download_url = f"https://{workspace_url}/files/{file_name}"
displayHTML(f'<a href="{download_url}" target="_blank">⬇️ Download {file_name}</a>')


