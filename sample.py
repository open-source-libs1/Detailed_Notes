

rebateOutput = spark.read.format("delta").load('abfss://gold@sbmuscapfdatala.../RebateSummarization')
rebateOutput.createOrReplaceTempView("Rebate")
