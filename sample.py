import pandas as pd

# Convert to Pandas for Excel export
df_pandas = df_compare_spark.toPandas()

# Define output path
excel_name = f"output_accuracy_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
local_path = f"/dbfs/tmp/{excel_name}"  # temp save in DBFS

# Save Excel
df_pandas.to_excel(local_path, index=False)
print(f"✅ Saved Excel to: {local_path}")

# Now copy Excel file to your ADLS path
adls_path = f"abfss://gold@sapbmuscafpdatalakeqa.dfs.core.windows.net/compengine/tmp/{excel_name}"
dbutils.fs.cp(f"dbfs:/tmp/{excel_name}", adls_path)
print(f"✅ Copied Excel to ADLS: {adls_path}")
