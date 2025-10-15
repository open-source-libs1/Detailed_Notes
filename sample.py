# assumes you already built df_compare_spark and 'now' as in your cell

base_dir = "abfss://gold@sapbmuscafpdatalakeqa.dfs.core.windows.net/compengine/tmp/test"

# --- keep your Delta output (already working)
delta_dir = f"{base_dir}/output_accuracy_F1A1F763C59542998D7BA67110BE99BA_{now}"
try:
    dbutils.fs.rm(delta_dir, recurse=True)
except:
    pass
df_compare_spark.write.format("delta").mode("overwrite").save(delta_dir)
print(f"✅ Wrote Delta: {delta_dir}")

# --- write a SINGLE CSV directly to ABFSS (no installs)
csv_base = f"Output_accuracy_{now}"
tmp_csv_dir = f"{base_dir}/tmp{csv_base}_csv"   # Spark writes a folder of parts
final_csv   = f"{base_dir}/{csv_base}.csv"        # we’ll move the single part here

# 1) coalesce to 1 partition so we get exactly one CSV part file
(df_compare_spark.coalesce(1)
  .write
  .option("header", "true")
  .mode("overwrite")
  .csv(tmp_csv_dir))

# 2) find the produced part-*.csv and move/rename to a clean single-file path
csv_part = [f.path for f in dbutils.fs.ls(tmp_csv_dir) if f.path.lower().endswith(".csv")][0]
dbutils.fs.mv(csv_part, final_csv, True)
dbutils.fs.rm(tmp_csv_dir, recurse=True)

print(f"✅ Wrote CSV to ADLS: {final_csv}")

# --- optional: also make an easy browser download copy (bypasses the 10 MB Workspace limit)
files_dir = "dbfs:/FileStore/exports"
dbutils.fs.mkdirs(files_dir)
download_csv = f"{files_dir}/{csv_base}.csv"
dbutils.fs.cp(final_csv, download_csv, True)

try:
    host = dbutils.notebook.entry_point.getDbutils().notebook().getContext().browserHostName().get()
    print(f"🔗 Download URL: https://{host}/files/exports/{csv_base}.csv")
except:
    pass
