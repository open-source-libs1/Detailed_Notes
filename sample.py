# Cell 1: Widgets / User inputs
# Purpose: drive environment, compared DB, and table category list.

mysql_key = "mysql"
postgres_key = "postgres"
starrocks_key = "starrocks"

property_columns_all = [
    "TABLE_SCHEMA",
    "TABLE_NAME",
    "COLUMN_NAME",
    "DATA_TYPE",
    "CHARACTER_MAXIMUM_LENGTH",
    "NUMERIC_PRECISION",
    "NUMERIC_SCALE",
    "IS_NULLABLE",
    "COLUMN_DEFAULT",
    "COLUMN_KEY",
    "ORDINAL_POSITION",
]

dbutils.widgets.multiselect("Property Columns", property_columns_all[0], property_columns_all)
dbutils.widgets.dropdown("Env", "QA", ["QA", "DEV", "PPRD", "PROD", "PRD"])
dbutils.widgets.dropdown("Compared DB", "StarRocks", ["StarRocks", "Postgres"])
dbutils.widgets.dropdown("Table Type", "Artifact", ["Artifact", "Input", "Output", "Staging"])

selected_property_columns = dbutils.widgets.get("Property Columns")
environment = dbutils.widgets.get("Env")
compared_db = dbutils.widgets.get("Compared DB")
table_type = dbutils.widgets.get("Table Type")

print("Selected Property Columns:", selected_property_columns)
print("Env:", environment)
print("Compared DB:", compared_db)
print("Table Type:", table_type)



######################################################

# Cell 2: Schema resolution + selection options
# Purpose: map table_type → mysql schema + compared schema + list of tables.

# --- MySQL schemas ---
mysql_artifact_schema = "comp_engine_microservice"
mysql_input_schema    = "comp_engine_microservice"
mysql_output_schema   = "comp_engine_microservice_output"
mysql_staging_schema  = "comp_engine_microservice"

# --- Postgres schemas if needed (kept for compatibility) ---
postgres_artifact_schema = "artifacts"
postgres_rebate_schema = "rebate"
postgres_rebate_output_schema = "rebate_output"

# --- StarRocks schemas (env-based like your snippet) ---
starrocks_artifact_schema = f"artifactsdb_{environment.lower()}"
starrocks_input_schema    = f"comp_engine_microservice_{environment.lower()}"
starrocks_output_schema   = f"comp_engine_microservice_output_{environment.lower()}"
starrocks_staging_schema  = f"stagedb_{environment.lower()}"

compared_key = ""
compared_artifact_schema = ""
compared_input_schema = ""
compared_output_schema = ""
compared_staging_schema = ""

if compared_db == "StarRocks":
    compared_key = starrocks_key
    compared_artifact_schema = starrocks_artifact_schema
    compared_input_schema    = starrocks_input_schema
    compared_output_schema   = starrocks_output_schema
    compared_staging_schema  = starrocks_staging_schema
else:
    compared_key = postgres_key
    compared_artifact_schema = postgres_artifact_schema
    compared_input_schema    = postgres_rebate_schema
    compared_output_schema   = postgres_rebate_output_schema
    compared_staging_schema  = postgres_rebate_schema

# ---- Your helper functions must exist ----
# def get_artifact_tables(): ...
# def get_input_tables(): ...
# def get_output_tables(): ...
# def get_staging_tables(): ...

selection_options = {
    "Artifact": {
        mysql_key: mysql_artifact_schema,
        "compared_schema": compared_artifact_schema,
        "tables": get_artifact_tables(),
    },
    "Input": {
        mysql_key: mysql_input_schema,
        "compared_schema": compared_input_schema,
        "tables": get_input_tables(),
    },
    "Output": {
        mysql_key: mysql_output_schema,
        "compared_schema": compared_output_schema,
        "tables": get_output_tables(),
    },
    "Staging": {
        mysql_key: mysql_staging_schema,
        "compared_schema": compared_staging_schema,
        "tables": get_staging_tables(),
    },
}

reference_tables = selection_options[table_type]["tables"]
mysql_schema = selection_options[table_type][mysql_key]
compared_schema = selection_options[table_type]["compared_schema"]

print("MySQL schema:", mysql_schema)
print("Compared schema:", compared_schema)
print("Num tables:", len(reference_tables))



#########################################

# Cell 3: Ignore columns + datatype normalization

import re
import pandas as pd

IGNORE_COLUMNS = {"createdAt", "updatedAt"}  # case-insensitive

MYSQL_TO_SR_CANON = {
    "int": "int", "integer": "int", "tinyint": "int", "smallint": "int", "bigint": "bigint", "bit": "int",
    "float": "float", "double": "double", "decimal": "decimal",
    "datetime": "datetime", "timestamp": "datetime", "date": "date", "time": "time",
    "char": "varchar", "varchar": "varchar", "text": "varchar", "longtext": "varchar", "mediumtext": "varchar",
    "json": "json",
    "binary": "varchar", "varbinary": "varchar", "blob": "varchar", "longblob": "varchar",
    "enum": "varchar", "set": "varchar",
}

SR_TO_CANON = {
    "int": "int", "bigint": "bigint", "smallint": "int", "tinyint": "int",
    "double": "double", "float": "float", "decimal": "decimal",
    "date": "date", "datetime": "datetime", "timestamp": "datetime",
    "varchar": "varchar", "char": "varchar", "string": "varchar",
    "json": "json", "boolean": "int",
}

def _base_type(dtype):
    if dtype is None:
        return ""
    return re.split(r"[\s(]", str(dtype).strip().lower())[0]

def normalize_mysql_dtype(dtype, char_len=None, num_precision=None, num_scale=None):
    bt = _base_type(dtype)
    canon = MYSQL_TO_SR_CANON.get(bt, bt)

    if canon == "decimal":
        p = int(num_precision) if pd.notna(num_precision) else None
        s = int(num_scale) if pd.notna(num_scale) else None
        return f"decimal({p},{s})" if p is not None and s is not None else "decimal"

    if canon == "varchar":
        l = int(char_len) if pd.notna(char_len) else None
        return f"varchar({l})" if l else "varchar"

    return canon

def normalize_starrocks_dtype(dtype, char_len=None, num_precision=None, num_scale=None):
    bt = _base_type(dtype)
    canon = SR_TO_CANON.get(bt, bt)

    if canon == "decimal":
        p = int(num_precision) if pd.notna(num_precision) else None
        s = int(num_scale) if pd.notna(num_scale) else None
        return f"decimal({p},{s})" if p is not None and s is not None else "decimal"

    if canon == "varchar":
        l = int(char_len) if pd.notna(char_len) else None
        return f"varchar({l})" if l else "varchar"

    return canon



###############################


# Cell 4: Queries + wrappers

MYSQL_COLUMNS_QUERY = """
SELECT
    TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE,
    IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY, ORDINAL_POSITION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = '{schema}'
  AND TABLE_NAME IN ({tables})
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""

COMPARED_COLUMNS_QUERY = """
SELECT
    TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE,
    IS_NULLABLE, COLUMN_DEFAULT, ORDINAL_POSITION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = '{schema}'
  AND TABLE_NAME IN ({tables})
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""

MYSQL_PK_QUERY = """
SELECT k.TABLE_NAME, k.COLUMN_NAME, k.ORDINAL_POSITION
FROM information_schema.KEY_COLUMN_USAGE k
JOIN information_schema.TABLE_CONSTRAINTS c
  ON k.CONSTRAINT_NAME = c.CONSTRAINT_NAME
 AND k.TABLE_SCHEMA = c.TABLE_SCHEMA AND k.TABLE_NAME = c.TABLE_NAME
WHERE c.CONSTRAINT_TYPE = 'PRIMARY KEY'
  AND k.TABLE_SCHEMA = '{schema}'
  AND k.TABLE_NAME IN ({tables})
ORDER BY k.TABLE_NAME, k.ORDINAL_POSITION
"""

MYSQL_UNIQUE_QUERY = """
SELECT s.TABLE_NAME, s.INDEX_NAME, s.COLUMN_NAME, s.SEQ_IN_INDEX
FROM information_schema.STATISTICS s
WHERE s.TABLE_SCHEMA = '{schema}'
  AND s.TABLE_NAME IN ({tables})
  AND s.NON_UNIQUE = 0
ORDER BY s.TABLE_NAME, s.INDEX_NAME, s.SEQ_IN_INDEX
"""

STARROCKS_SHOW_CREATE = "SHOW CREATE TABLE {schema}.{table}"

def quote_list(vals):
    return ",".join([f"'{v}'" for v in vals])

def run_mysql(schema, query):
    return mysqlConnection(schema, query)

def run_starrocks(schema, query):
    return starrocksConnection(schema, query)




####################################


# Cell 5: DEBUG A
# Purpose: if something fails, you can see exact queries.

print("---- MySQL columns query ----")
print(MYSQL_COLUMNS_QUERY.format(schema=mysql_schema, tables=quote_list(reference_tables[:5])))

print("\n---- Compared columns query ----")
print(COMPARED_COLUMNS_QUERY.format(schema=compared_schema, tables=quote_list(reference_tables[:5])))

print("\n---- MySQL PK query ----")
print(MYSQL_PK_QUERY.format(schema=mysql_schema, tables=quote_list(reference_tables[:5])))

print("\n---- MySQL unique query ----")
print(MYSQL_UNIQUE_QUERY.format(schema=mysql_schema, tables=quote_list(reference_tables[:5])))



#######################



# Cell 6: Fetch schema + MySQL keys

def fetch_columns(schema, tables, db_key):
    if not tables:
        return pd.DataFrame()
    q = (MYSQL_COLUMNS_QUERY if db_key == mysql_key else COMPARED_COLUMNS_QUERY).format(
        schema=schema, tables=quote_list(tables)
    )
    df = run_mysql(schema, q) if db_key == mysql_key else run_starrocks(schema, q)
    df.columns = [c.upper() for c in df.columns]
    return df

def fetch_mysql_keys(schema, tables):
    if not tables:
        return pd.DataFrame(), pd.DataFrame()
    tlist = quote_list(tables)

    pk = run_mysql(schema, MYSQL_PK_QUERY.format(schema=schema, tables=tlist))
    uq = run_mysql(schema, MYSQL_UNIQUE_QUERY.format(schema=schema, tables=tlist))

    pk.columns = [c.upper() for c in pk.columns]
    uq.columns = [c.upper() for c in uq.columns]
    return pk, uq

mysql_cols = fetch_columns(mysql_schema, reference_tables, mysql_key)
compared_cols = fetch_columns(compared_schema, reference_tables, compared_key)
mysql_pk_df, mysql_uq_df = fetch_mysql_keys(mysql_schema, reference_tables)



###########################

# Cell 7: Normalize column metadata for fair comparison

def prepare_columns_df(df, db_kind):
    if df.empty:
        return df
    df = df.copy()
    df["COLUMN_NAME_UPPER"] = df["COLUMN_NAME"].str.upper()
    df["IS_NULLABLE"] = df["IS_NULLABLE"].str.upper()

    if db_kind == "mysql":
        df["NORMALIZED_DATA_TYPE"] = df.apply(
            lambda r: normalize_mysql_dtype(
                r["DATA_TYPE"], r.get("CHARACTER_MAXIMUM_LENGTH"),
                r.get("NUMERIC_PRECISION"), r.get("NUMERIC_SCALE")
            ),
            axis=1
        )
    else:
        df["NORMALIZED_DATA_TYPE"] = df.apply(
            lambda r: normalize_starrocks_dtype(
                r["DATA_TYPE"], r.get("CHARACTER_MAXIMUM_LENGTH"),
                r.get("NUMERIC_PRECISION"), r.get("NUMERIC_SCALE")
            ),
            axis=1
        )
    return df

mysql_cols = prepare_columns_df(mysql_cols, "mysql")
compared_cols = prepare_columns_df(compared_cols, "starrocks" if compared_key == starrocks_key else "postgres")




############################

# Cell 8: StarRocks DDL parsing for keys
# Matches your sample:
#   DUPLICATE KEY(`uw_req_id`)
#   ORDER BY(`uw_req_id`, `lob_id`, ...)

def fetch_starrocks_ddl(schema, table):
    ddl_df = run_starrocks(schema, STARROCKS_SHOW_CREATE.format(schema=schema, table=table))
    if ddl_df.empty:
        return ""
    return str(ddl_df.iloc[0, 1])  # create stmt

def parse_starrocks_keys_from_ddl(ddl):
    ddl_l = ddl.lower()

    def extract_cols(keyword):
        m = re.search(rf"{keyword}\s*\((.*?)\)", ddl_l, re.S)
        if not m:
            return []
        cols = [c.strip().strip("`").strip('"') for c in m.group(1).split(",")]
        return [c.upper() for c in cols if c]

    key_model = "UNKNOWN"
    key_cols = []
    unique_cols = []
    order_by_cols = []

    if "primary key" in ddl_l:
        key_model = "PRIMARY KEY"
        key_cols = extract_cols("primary key")
    elif "unique key" in ddl_l:
        key_model = "UNIQUE KEY"
        key_cols = extract_cols("unique key")
        unique_cols = key_cols[:]
    elif "duplicate key" in ddl_l:
        key_model = "DUPLICATE KEY"
        key_cols = extract_cols("duplicate key")
    elif "aggregate key" in ddl_l:
        key_model = "AGGREGATE KEY"
        key_cols = extract_cols("aggregate key")

    if "order by" in ddl_l:
        order_by_cols = extract_cols("order by")

    if not unique_cols and "unique key" in ddl_l:
        unique_cols = extract_cols("unique key")

    return {
        "SR_KEY_MODEL": key_model,
        "SR_KEY_COLUMNS": key_cols,
        "SR_UNIQUE_COLUMNS": unique_cols,
        "SR_ORDER_BY_COLUMNS": order_by_cols,
    }



###################

# Cell 9: DEBUG B
# Call this for any table to see its DDL + parsed keys.

def debug_starrocks_ddl(table):
    ddl = fetch_starrocks_ddl(compared_schema, table)
    parsed = parse_starrocks_keys_from_ddl(ddl)
    print(f"\n--- DDL for {compared_schema}.{table} ---\n")
    print(ddl)
    print("\n--- Parsed ---")
    print(parsed)



########################

# Cell 10: Column-level compare

def compare_table_columns(mysql_t, compared_t, ignore_columns):
    ignore_upper = {c.upper() for c in ignore_columns}

    m = mysql_t[~mysql_t["COLUMN_NAME_UPPER"].isin(ignore_upper)]
    s = compared_t[~compared_t["COLUMN_NAME_UPPER"].isin(ignore_upper)]

    m_cols = set(m["COLUMN_NAME_UPPER"])
    s_cols = set(s["COLUMN_NAME_UPPER"])
    all_cols = sorted(m_cols.union(s_cols))

    m_idx = m.set_index("COLUMN_NAME_UPPER")
    s_idx = s.set_index("COLUMN_NAME_UPPER")

    rows = []
    for c in all_cols:
        mrow = m_idx.loc[c] if c in m_idx.index else None
        srow = s_idx.loc[c] if c in s_idx.index else None

        if mrow is None:
            rows.append({"COLUMN_NAME": c, "STATUS": "MISSING_IN_MYSQL"})
            continue
        if srow is None:
            rows.append({"COLUMN_NAME": c, "STATUS": "MISSING_IN_COMPARED"})
            continue

        diffs = {}
        checks = [
            ("NORMALIZED_DATA_TYPE", "DATA_TYPE"),
            ("IS_NULLABLE", "IS_NULLABLE"),
            ("CHARACTER_MAXIMUM_LENGTH", "CHARACTER_MAXIMUM_LENGTH"),
            ("NUMERIC_PRECISION", "NUMERIC_PRECISION"),
            ("NUMERIC_SCALE", "NUMERIC_SCALE"),
            ("COLUMN_DEFAULT", "COLUMN_DEFAULT"),
        ]

        for norm_key, raw_key in checks:
            mv = mrow.get(norm_key, mrow.get(raw_key))
            sv = srow.get(norm_key, srow.get(raw_key))
            if pd.isna(mv) and pd.isna(sv):
                continue
            if str(mv) != str(sv):
                diffs[raw_key] = {"mysql": mv, "compared": sv}

        rows.append({"COLUMN_NAME": c, "STATUS": "MATCH" if not diffs else "DIFF", "DIFFS": diffs})

    return pd.DataFrame(rows)



##########################


# Cell 11: Key compare

def mysql_pk_list(df_pk, table):
    d = df_pk[df_pk["TABLE_NAME"].str.lower() == table.lower()]
    return d.sort_values("ORDINAL_POSITION")["COLUMN_NAME"].str.upper().tolist()

def mysql_unique_indexes(df_uq, table):
    d = df_uq[df_uq["TABLE_NAME"].str.lower() == table.lower()].copy()
    if d.empty:
        return {}
    out = {}
    for idx, grp in d.groupby("INDEX_NAME"):
        cols = grp.sort_values("SEQ_IN_INDEX")["COLUMN_NAME"].str.upper().tolist()
        out[str(idx).upper()] = cols
    return out

def compare_keys(table):
    m_pk = mysql_pk_list(mysql_pk_df, table)
    m_uq = mysql_unique_indexes(mysql_uq_df, table)

    ddl = fetch_starrocks_ddl(compared_schema, table) if compared_key == starrocks_key else ""
    sr_parsed = parse_starrocks_keys_from_ddl(ddl) if ddl else {
        "SR_KEY_MODEL": "N/A", "SR_KEY_COLUMNS": [], "SR_UNIQUE_COLUMNS": [], "SR_ORDER_BY_COLUMNS": []
    }

    pk_match = (sr_parsed["SR_KEY_MODEL"] == "PRIMARY KEY" and m_pk == sr_parsed["SR_KEY_COLUMNS"])

    unique_match = True
    if m_uq:
        mysql_unique_sets = [tuple(v) for v in m_uq.values()]
        unique_match = (tuple(sr_parsed["SR_UNIQUE_COLUMNS"]) in mysql_unique_sets) if sr_parsed["SR_UNIQUE_COLUMNS"] else False

    return {
        "MYSQL_PK": m_pk,
        "MYSQL_UNIQUE": m_uq,
        **sr_parsed,
        "PK_MATCH": pk_match,
        "UNIQUE_MATCH": unique_match,
    }




#################################


# Cell 12: DEBUG C
# If a table fails, we surface it immediately with extra context.

def debug_table(table):
    print(f"\n### DEBUG TABLE: {table} ###")
    m_t = mysql_cols[mysql_cols["TABLE_NAME"].str.lower() == table.lower()]
    s_t = compared_cols[compared_cols["TABLE_NAME"].str.lower() == table.lower()]
    print("MySQL columns:", len(m_t), "Compared columns:", len(s_t))
    if compared_key == starrocks_key:
        debug_starrocks_ddl(table)




#####################################



# Cell 13: Run comparisons + summary/detail reports

from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()

detail_results = {}
key_results = []
summary_rows = []

for t in reference_tables:
    try:
        m_t = mysql_cols[mysql_cols["TABLE_NAME"].str.lower() == t.lower()]
        s_t = compared_cols[compared_cols["TABLE_NAME"].str.lower() == t.lower()]

        col_diff_df = compare_table_columns(m_t, s_t, IGNORE_COLUMNS)
        detail_results[t] = col_diff_df

        key_diff = compare_keys(t)
        key_results.append({"TABLE_NAME": t, **key_diff})

        issues = col_diff_df[col_diff_df["STATUS"].isin(["DIFF","MISSING_IN_MYSQL","MISSING_IN_COMPARED"])]
        summary_rows.append({
            "TABLE_NAME": t,
            "COLUMN_PASS": issues.empty,
            "NUM_COLUMN_ISSUES": int(len(issues)),
            "PK_MATCH": key_diff["PK_MATCH"],
            "UNIQUE_MATCH": key_diff["UNIQUE_MATCH"],
            "SR_KEY_MODEL": key_diff["SR_KEY_MODEL"],
            "OVERALL_PASS": (issues.empty and key_diff["PK_MATCH"] and key_diff["UNIQUE_MATCH"]),
        })

    except Exception as e:
        print(f"[ERROR] Table={t} failed: {e}")
        debug_table(t)
        summary_rows.append({
            "TABLE_NAME": t,
            "COLUMN_PASS": False,
            "NUM_COLUMN_ISSUES": -1,
            "PK_MATCH": False,
            "UNIQUE_MATCH": False,
            "SR_KEY_MODEL": "ERROR",
            "OVERALL_PASS": False,
            "ERROR": str(e),
        })



##########################


# Cell 14: Summary + key results

summary_df = pd.DataFrame(summary_rows).sort_values("TABLE_NAME")
keys_df = pd.DataFrame(key_results).sort_values("TABLE_NAME")

# Optional: filter output columns based on widget "Property Columns"
selected_cols_list = [c.strip().upper() for c in selected_property_columns.split(",") if c.strip()]
# summary_df doesn't need filtering; keys_df also doesn't.
# detail view will still show diffs fully (better for debugging).

display(spark.createDataFrame(summary_df))
display(spark.createDataFrame(keys_df))




############################


# Cell 15: Detailed diffs per table

for t, df in detail_results.items():
    print(f"\n===== {t} (Schema diff) =====")
    display(spark.createDataFrame(df))









