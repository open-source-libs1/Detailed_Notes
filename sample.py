from pyspark.sql import functions as F

# Query to fetch completed records from the last 4 hours
query = """
SELECT DISTINCT
    UPPER(REPLACE(BIN_TO_UUID(scenario_id), '-', '')) AS scenario_id,
    lob_id,
    UPPER(REPLACE(BIN_TO_UUID(uw_req_id), '-', '')) AS uw_req_id,
    started_at,
    updated_at,
    status
FROM comp_engine_microservice.model_parameters
WHERE updated_at >= NOW() - INTERVAL 4 HOUR
  AND status = 'Completed';
"""

# Fetch data
mysql_df = mysqlConnection('comp_engine_microservice', query).collect()
starrocks_df = mystarrocksConnection('comp_engine_microservice', query).collect()

# Calculate duration (in seconds)
mysql_df = mysql_df.withColumn(
    "mysql_duration_seconds",
    (F.unix_timestamp("updated_at") - F.unix_timestamp("started_at"))
)

starrocks_df = starrocks_df.withColumn(
    "starrocks_duration_seconds",
    (F.unix_timestamp("updated_at") - F.unix_timestamp("started_at"))
)

# Join on keys to compare durations
comparison_df = mysql_df.alias("m").join(
    starrocks_df.alias("s"),
    on=["scenario_id", "lob_id", "uw_req_id"],
    how="inner"
).select(
    "scenario_id",
    "lob_id",
    "uw_req_id",
    F.col("m.mysql_duration_seconds"),
    F.col("s.starrocks_duration_seconds"),
    (F.col("s.starrocks_duration_seconds") - F.col("m.mysql_duration_seconds")).alias("duration_diff_seconds")
)

# Add human-readable comment column
comparison_df = comparison_df.withColumn(
    "duration_diff_comment",
    F.when(F.col("duration_diff_seconds") > 0,
           F.concat(F.lit("StarRocks took "), F.col("duration_diff_seconds").cast("int"), F.lit(" seconds more than MySQL")))
    .when(F.col("duration_diff_seconds") < 0,
          F.concat(F.lit("MySQL took "), F.abs(F.col("duration_diff_seconds")).cast("int"), F.lit(" seconds more than StarRocks")))
    .otherwise(F.lit("Both took equal time"))
)

# Display results
display(comparison_df)
