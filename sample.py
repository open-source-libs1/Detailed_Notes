def compare_basic(tables, mysql_db, sr_db):
    results = []

    for t in tables:
        print(f"\n============================")
        print(f"Comparing table: {t}")
        print(f"============================")

        # Build queries
        mysql_q = f"SELECT * FROM {mysql_db}.{t}"
        sr_q    = f"SELECT * FROM {sr_db}.{t}"

        print("MySQL Query     :", mysql_q)
        print("StarRocks Query :", sr_q)

        # Execute queries
        mysql_df = mysqlConnection(mysql_db, mysql_q)
        sr_df    = starrocksConnection(sr_db, sr_q)

        # Row counts
        mysql_count = mysql_df.count()
        sr_count    = sr_df.count()

        # Columns
        mysql_cols = set(mysql_df.columns)
        sr_cols    = set(sr_df.columns)

        col_diff_mysql_only = sorted(list(mysql_cols - sr_cols))
        col_diff_sr_only    = sorted(list(sr_cols - mysql_cols))

        # Print summary
        print(f"MySQL Row Count     : {mysql_count}")
        print(f"StarRocks Row Count : {sr_count}")
        print(f"Row Count Match?    : {mysql_count == sr_count}")

        print(f"Columns in MySQL not in SR : {col_diff_mysql_only}")
        print(f"Columns in SR not in MySQL : {col_diff_sr_only}")
        print(f"Column Match?               : {len(col_diff_mysql_only)==0 and len(col_diff_sr_only)==0}")

        results.append({
            "table": t,
            "mysql_count": mysql_count,
            "sr_count": sr_count,
            "mysql_only_cols": col_diff_mysql_only,
            "sr_only_cols": col_diff_sr_only
        })

    return results
