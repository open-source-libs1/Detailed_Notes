from pyspark.sql.functions import col, when

condition_col = "Final_Network"
condition_exp = None

# ✅ Spark Connect-safe check for non-empty DataFrame
if All_Revenue_Combined_NPGs_DF.limit(1).count() > 0:
    for condition_val, cat_name in final_network_conditions:
        if condition_exp is None:
            condition_exp = when(condition_val, cat_name)
        else:
            condition_exp = condition_exp.when(condition_val, cat_name)

    All_Revenue_Combined_NPGs_DF = All_Revenue_Combined_NPGs_DF.withColumn(
        condition_col, condition_exp.otherwise("NA")
    )

else:
    print("⚠️ No records present for the Scenario ID")
    decimal_columns_to_cast = [
        "NumClaims", "AWP_Total", "Acquisition_Cost",
        "Cogs_Trad_PBM_Total", "Cogs_Trans_PBM_Total",
        "Cogs_Dispns_Fee_Trans_PBM_Total", "Cogs_Trad_Medi_Total",
        "Cogs_Trans_Medi_Total", "Cogs_Dispns_Fee_Trad_Medi_Total"
    ]

    for clm in decimal_columns_to_cast:
        All_Revenue_Combined_NPGs_DF = All_Revenue_Combined_NPGs_DF.withColumn(
            clm, col(clm).cast("double")
        )
