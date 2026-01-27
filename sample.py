from pyspark.sql.functions import col, when, lit

df = All_Revenue_Combined_NPGs_DF
condition_col = "Final_Network"

# Safer/cheaper emptiness check than full count() (and avoids overwriting df)
if df is None or len(df.take(1)) == 0:
    print("No records present for the Scenario ID")
else:
    # Build chained when() expression
    condition_exp = None
    for condition_val, cat_name in final_network_conditions:
        if condition_exp is None:
            condition_exp = when(condition_val, lit(cat_name))
        else:
            condition_exp = condition_exp.when(condition_val, lit(cat_name))

    df = df.withColumn(condition_col, condition_exp.otherwise(lit("NA")))

    # Cast columns (runs only when df is a real DataFrame)
    decimal_columns_to_cast = [
        "NumClaims","AWP_Total","Acquisition_Cost","Cogs_Trad_PBM_Total",
        "Cogs_Dispns_Fee_Trans_PBM_Total","Cogs_Trad_Medi_Total",
        "Cogs_Trans_Medi_Total","Cogs_Dispns_Fee_Trad_Medi_Total"
    ]
    for clm in decimal_columns_to_cast:
        if clm in df.columns:
            df = df.withColumn(clm, col(clm).cast("double"))

All_Revenue_Combined_NPGs_DF = df
