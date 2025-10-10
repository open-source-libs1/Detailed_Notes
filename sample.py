from pyspark.sql import functions as F

# 1) CE - detail
ce_detail_table = "puma_qa.quality_platform.qa_ce_stage_qp_detail_table"
tgt = spark.table(ce_detail_table)
to_write = ce_regression_detail_daily_result.select([F.col(c) for c in tgt.columns])
to_write.write.mode("append").insertInto(ce_detail_table)

# 2) CE - summary
ce_summary_table = "puma_qa.quality_platform.qa_ce_stage_qp_summary_table"
tgt = spark.table(ce_summary_table)
to_write = ce_regression_summary_daily_result.select([F.col(c) for c in tgt.columns])
to_write.write.mode("append").insertInto(ce_summary_table)

# 3) DFM - detail
dfm_detail_table = "puma_qa.quality_platform.eos_qp_t_test_run_status"
tgt = spark.table(dfm_detail_table)
to_write = dfm_regression_detail_daily_result.select([F.col(c) for c in tgt.columns])
to_write.write.mode("append").insertInto(dfm_detail_table)

# 4) DFM - summary
dfm_summary_table = "puma_qa.quality_platform.eos_qp_t_test_run_dtl_status"
tgt = spark.table(dfm_summary_table)
to_write = dfm_regression_summary_daily_result.select([F.col(c) for c in tgt.columns])
to_write.write.mode("append").insertInto(dfm_summary_table)


for name, df, tbl in [
    ("CE detail", ce_regression_detail_daily_result, ce_detail_table),
    ("CE summary", ce_regression_summary_daily_result, ce_summary_table),
    ("DFM detail", dfm_regression_detail_daily_result, dfm_detail_table),
    ("DFM summary", dfm_regression_summary_daily_result, dfm_summary_table),
]:
    assert df.limit(1).count() > 0, f"{name} DF is empty"
    assert set(df.columns) >= set(spark.table(tbl).columns), f"{name} DF missing columns for {tbl}"
