rebateOutput = spark.table("puma_qa.ce.rebate_summarization")
rebateOutput.createOrReplaceTempView("Rebate")
