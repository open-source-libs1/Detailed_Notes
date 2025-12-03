df_compare_spark = df_compare_spark.toDF(
    *[re.sub(r"[^\w]", "_", c) for c in df_compare_spark.columns]
)
