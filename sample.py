from pyspark.sql.functions import when, col, lit

condition_col = "Final_Network"

# Spark Connect-safe emptiness check
is_empty = Excl_Revenue_Combined_NPG_DF.limit(1).count() == 0

if not is_empty:
    condition_exp = None
    for condition_val, cat_name in final_network_conditions:
        condition_exp = when(condition_val, lit(cat_name)) if condition_exp is None \
                        else condition_exp.when(condition_val, lit(cat_name))
    Excl_Revenue_Combined_NPG_DF = (
        Excl_Revenue_Combined_NPG_DF
        .withColumn(condition_col, condition_exp.otherwise(lit("Unknown")))
    )
else:
    # Keep a DataFrame (not a string) so downstream code still works
    if condition_col not in Excl_Revenue_Combined_NPG_DF.columns:
        Excl_Revenue_Combined_NPG_DF = Excl_Revenue_Combined_NPG_DF.withColumn(
            condition_col, lit(None).cast("string")
        )
    # Optional: log/message instead of overwriting the DF
    print("No records present for the Scenario ID")

# Safe casting (works even if the DF is empty)
decimal_columns_to_cast = [
    "NumClaims","AWP_Total","Acquisition_Cost","Cogs_Trad_PBM_Total",
    "Cogs_Trans_PBM_Total","Cogs_Dispsn_Fee_Trans_PBM_Total",
    "Cogs_Trad_Medi_Total","Cogs_Trans_Medi_Total",
    "Cogs_Dispsn_Fee_Trad_Medi_Total"
]
for clm in decimal_columns_to_cast:
    if clm in Excl_Revenue_Combined_NPG_DF.columns:
        Excl_Revenue_Combined_NPG_DF = Excl_Revenue_Combined_NPG_DF.withColumn(
            clm, col(clm).cast("double")
        )
