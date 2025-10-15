# you already have df_compare_spark and now
base_dir = "abfss://gold@sapbmuscafpdatalakeqa.dfs.core.windows.net/compengine/tmp"

# ---- keep your Delta write (already in your screenshot)
temp_path = f"{base_dir}/output_accuracy_F1A1F763C59542998D7BA67110BE99BA_{now}"
try:
    dbutils.fs.rm(temp_path, recurse=True)
except:
    pass
df_compare_spark.write.format("delta").mode("overwrite").save(temp_path)
print(f"✅ Wrote Delta: {temp_path}")

# ---- write Excel directly to ABFSS (no DBFS, no SDK)
excel_base = f"Output_accuracy_{now}"
tmp_excel_dir = f"{base_dir}/tmp{excel_base}"     # spark-excel writes into a dir
final_excel = f"{base_dir}/{excel_base}.xlsx"       # we’ll move the produced file here

# ensure parent exists
dbutils.fs.mkdirs(base_dir)

# 1) create exactly one .xlsx by coalescing to 1 partition
(df_compare_spark.coalesce(1)
 .write
 .format("com.crealytics.spark.excel")
 .option("header", "true")
 .mode("overwrite")
 .save(tmp_excel_dir))   # this creates a part-0000....xlsx inside tmp_excel_dir

# 2) move the produced .xlsx out of the temp dir to a clean single-file path
xlsx_part = [f.path for f in dbutils.fs.ls(tmp_excel_dir) if f.path.lower().endswith(".xlsx")][0]
dbutils.fs.mv(xlsx_part, final_excel, True)
dbutils.fs.rm(tmp_excel_dir, recurse=True)

print(f"✅ Wrote Excel: {final_excel}")
dbutils.notebook.exit(final_excel)   # or return whatever path you prefer
