
from pyspark.sql import functions as F

target_tbl = "puma_qa.quality_platform.qa_ce_stage_qp_detail_table"

# 1) Make sure the columns and types match the table
tgt = spark.table(target_tbl)
tgt_cols = tgt.columns                     # preserves the table's column order

# (Optional) quick check
# display(tgt.limit(1)); ce_regression_detail_daily_result.printSchema(); tgt.printSchema()

# 2) Re-select/reorder to match the table schema
to_write = ce_regression_detail_daily_result.select([F.col(c) for c in tgt_cols])

# 3) Append to the table
# Option 1: works for Hive/Parquet/Delta when table already exists and schema matches
to_write.write.mode("append").insertInto(target_tbl)

# If insertInto is not enabled in your workspace, use:
# to_write.write.mode("append").saveAsTable(target_tbl)
