from pyspark.sql.functions import when, col

# Update logic for CE Summary table
ce_regression_summary_daily_result = (
    ce_regression_summary_daily_result
    .withColumn(
        "EXECUTION_STATUS",
        when(col("SUCCESS_CNT") > 0, "COMPLETED").otherwise(col("EXECUTION_STATUS"))
    )
    .withColumn(
        "TS_STATUS",
        when(col("SUCCESS_CNT") > 0, "PASS").otherwise(col("TS_STATUS"))
    )
    .withColumn(
        "FAILURE_CNT",
        when(col("SUCCESS_CNT") > 0, 0).otherwise(col("FAILURE_CNT"))
    )
    .withColumn(
        "TOTAL_CNT",
        when(col("SUCCESS_CNT") > 0, col("SUCCESS_CNT")).otherwise(col("TOTAL_CNT"))
    )
)

# Then continue as before
ce_regression_summary_daily_result = ce_regression_summary_daily_result.select(
    "RUN_ID", "TQ_CD", "TS_CTG", "PARENT_REQUEST_ID", "REQUEST_ID",
    "TASK_ID", "EXECUTION_STATUS", "TS_STATUS", "TOTAL_CNT",
    "SUCCESS_CNT", "FAILURE_CNT", "RUN_DATE_TS", "RUN_USER"
)

display(ce_regression_summary_daily_result)
