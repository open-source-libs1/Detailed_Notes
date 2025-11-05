# Rebate
rebateOutput = spark.table("puma_qa.ce.rebate_summarization")
rebateOutput.createOrReplaceTempView("Rebate")

# Specialty
specialtyOutput = spark.table("puma_qa.ce.specialty_summarization")
specialtyOutput.createOrReplaceTempView("Specialty")

# Revenue
revenueOutput = spark.table("puma_qa.ce.revenue_summarization")
revenueOutput.createOrReplaceTempView("Revenue")
