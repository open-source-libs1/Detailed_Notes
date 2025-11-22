import pyspark.sql.functions as F
from pyspark.sql import DataFrame


def compare_tables_and_store(tables, mysql_db, sr_db, sample_limit=5):
    results = []
    mismatches = []

    for t in tables:
        print("\n=======================================")
        print(f"🔍 Comparing Table: {t}")
        print("=======================================")

        mysql_q = f"SELECT * FROM {mysql_db}.{t}"
        sr_q    = f"SELECT * FROM {sr_db}.{t}"

        print(f"MySQL Query     : {mysql_q}")
        print(f"StarRocks Query : {sr_q}")

        # Run queries
        mysql_df = mysqlConnection(mysql_db, mysql_q)
        sr_df    = starrocksConnection(sr_db, sr_q)

        # Row counts
        mysql_count = mysql_df.count()
        sr_count    = sr_df.count()

        print(f"MySQL Count     : {mysql_count}")
        print(f"StarRocks Count : {sr_count}")

        # Column comparison
        mysql_cols = set(mysql_df.columns)
        sr_cols    = set(sr_df.columns)

        cols_mysql_only = sorted(list(mysql_cols - sr_cols))
        cols_sr_only    = sorted(list(sr_cols - mysql_cols))

        print("Columns in MySQL not in SR:", cols_mysql_only)
        print("Columns in SR not in MySQL:", cols_sr_only)

        common_cols = sorted(list(mysql_cols & sr_cols))

        # Compute SHA256 hash for data comparison
        mysql_hash = mysql_df.select(
            F.sha2(F.concat_ws("||", *common_cols), 256).alias("hash")
        )
        sr_hash = sr_df.select(
            F.sha2(F.concat_ws("||", *common_cols), 256).alias("hash")
        )

        diff_mysql = mysql_hash.subtract(sr_hash)
        diff_sr    = sr_hash.subtract(mysql_hash)

        diff_mysql_count = diff_mysql.count()
        diff_sr_count    = diff_sr.count()

        print(f"Rows in MySQL not in SR : {diff_mysql_count}")
        print(f"Rows in SR not in MySQL : {diff_sr_count}")

        status = "MATCH"
        if diff_mysql_count > 0 or diff_sr_count > 0 or cols_mysql_only or cols_sr_only or mysql_count != sr_count:
            status = "MISMATCH"

        # Save summary
        results.append({
            "table": t,
            "mysql_count": mysql_count,
            "sr_count": sr_count,
            "row_count_match": mysql_count == sr_count,
            "cols_mysql_only": ", ".join(cols_mysql_only),
            "cols_sr_only": ", ".join(cols_sr_only),
            "data_mysql_only": diff_mysql_count,
            "data_sr_only": diff_sr_count,
            "status": status
        })

        # Store mismatch samples
        if status == "MISMATCH":
            mismatches.append({
                "table": t,
                "mysql_missing_rows": diff_mysql.limit(sample_limit).toPandas(),
                "sr_missing_rows": diff_sr.limit(sample_limit).toPandas()
            })

    return results, mismatches



#################


tables = [
    "admin_billing",
    "claims_billing",
    "opportunity",
    # add more ...
]

mysql_db = "comp_engine_microservice"
sr_db    = "artifactdb_prd"

summary_list, mismatches = compare_tables_and_store(tables, mysql_db, sr_db)

summary_df = spark.createDataFrame(summary_list)
display(summary_df)



##################
