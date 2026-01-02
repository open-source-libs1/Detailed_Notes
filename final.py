if hasattr(df, "toPandas"): df = df.toPandas()
elif hasattr(df, "to_pandas"): df = df.to_pandas()



/////



df[col] = df[col].astype(str).str.strip().str.lower().map({"true": True, "false": False, "1": True, "0": False, "yes": True, "no": False}).astype("boolean")
