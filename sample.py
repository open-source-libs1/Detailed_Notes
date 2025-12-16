NO_RECORDS_MSG = "No records present for the Parent Request ID"

if pre_dfm_output == NO_RECORDS_MSG:
    msg = f"Issue in PRE DFM request: {pre_dfm_output}"
    print(msg)
    dbutils.notebook.exit(msg)

elif post_dfm_output == NO_RECORDS_MSG:
    msg = f"Issue in POST DFM request: {post_dfm_output}"
    print(msg)
    dbutils.notebook.exit(msg)

else:
    pre_df  = spark.read.format("delta").load(pre_dfm_output)
    post_df = spark.read.format("delta").load(post_dfm_output)

    # Only do this if the data is small enough to fit in driver memory
    pre_pd  = pre_df.toPandas()
    post_pd = post_df.toPandas()

