
import pandas as pd
import os

# Create full export path
file_path = f"/Workspace/Shared/QA Test Automation/Star Rocks Migration/Validate_Table_Output/Latest-Sai/OCT-23/others/{output_name}{uw_req_id}_{time_stamp()}.xlsx"

# Ensure directory exists
os.makedirs(os.path.dirname(file_path), exist_ok=True)

# Write to a single Excel sheet
with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
    result_df.to_excel(writer, index=False, sheet_name="Results")

print(f"✅ Exported all results to one sheet: {file_path}")
