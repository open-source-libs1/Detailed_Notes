# schema_compare_library - Cell A1
# Purpose: shared utilities for schema comparison.

import re
import pandas as pd

def upper_cols(df):
    """
    Safely uppercases DF column names.
    - Spark DF: uses toDF (columns are read-only)
    - Pandas DF: assigns df.columns
    """
    if df is None:
        return df

    if hasattr(df, "toDF") and not isinstance(df, pd.DataFrame):
        return df.toDF(*[c.upper() for c in df.columns])

    df.columns = [c.upper() for c in df.columns]
    return df


def quote_list(vals):
    """Quote strings for SQL IN (...)"""
    return ",".join([f"'{v}'" for v in vals])

# schema_compare_library - Cell A2
# Purpose: normalize MySQL/StarRocks data types into a common form.

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


# schema_compare_library - Cell A3
# Purpose: standard metadata queries.

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

# schema_compare_library - Cell A4
# Purpose: fetch schema/keys from source or target.

def fetch_columns(schema, tables, db_key, mysql_key, run_mysql, run_starrocks):
    """
    Fetch columns for mysql or compared db.
    The run_* functions must accept (schema, query) and return Spark DF.
    """
    if not tables:
        return pd.DataFrame()

    q = (MYSQL_COLUMNS_QUERY if db_key == mysql_key else COMPARED_COLUMNS_QUERY).format(
        schema=schema, tables=quote_list(tables)
    )

    df = run_mysql(schema, q) if db_key == mysql_key else run_starrocks(schema, q)
    return upper_cols(df)


def fetch_mysql_keys(schema, tables, run_mysql):
    """Fetch MySQL PK + UNIQUE indexes."""
    if not tables:
        return pd.DataFrame(), pd.DataFrame()

    tlist = quote_list(tables)
    pk = run_mysql(schema, MYSQL_PK_QUERY.format(schema=schema, tables=tlist))
    uq = run_mysql(schema, MYSQL_UNIQUE_QUERY.format(schema=schema, tables=tlist))

    return upper_cols(pk), upper_cols(uq)


# schema_compare_library - Cell A5
# Purpose: add normalized dtype + helper columns to compare fairly.

def prepare_columns_df(df, db_kind):
    """
    Converts Spark → pandas for apply-based normalization.
    Adds:
      COLUMN_NAME_UPPER
      NORMALIZED_DATA_TYPE
      IS_NULLABLE upper
    """
    if df is None:
        return df

    if hasattr(df, "toPandas") and not isinstance(df, pd.DataFrame):
        df = df.toPandas()

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

# schema_compare_library - Cell A6
# Purpose: pull StarRocks SHOW CREATE TABLE and parse key model/cols.

def fetch_starrocks_ddl(schema, table, run_starrocks):
    ddl_df = run_starrocks(schema, STARROCKS_SHOW_CREATE.format(schema=schema, table=table))

    if ddl_df is None:
        return ""

    if hasattr(ddl_df, "toPandas") and not isinstance(ddl_df, pd.DataFrame):
        ddl_df = ddl_df.toPandas()

    if ddl_df.empty:
        return ""

    return str(ddl_df.iloc[0, 1])


def parse_starrocks_keys_from_ddl(ddl: str):
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

# schema_compare_library - Cell A7
# Purpose: actual comparison logic.

def compare_table_columns(source_t, target_t, ignore_columns):
    ignore_upper = {c.upper() for c in ignore_columns}

    s = source_t[~source_t["COLUMN_NAME_UPPER"].isin(ignore_upper)]
    t = target_t[~target_t["COLUMN_NAME_UPPER"].isin(ignore_upper)]

    s_cols = set(s["COLUMN_NAME_UPPER"])
    t_cols = set(t["COLUMN_NAME_UPPER"])
    all_cols = sorted(s_cols.union(t_cols))

    s_idx = s.set_index("COLUMN_NAME_UPPER")
    t_idx = t.set_index("COLUMN_NAME_UPPER")

    rows = []
    for c in all_cols:
        srow = s_idx.loc[c] if c in s_idx.index else None
        trow = t_idx.loc[c] if c in t_idx.index else None

        if srow is None:
            rows.append({"COLUMN_NAME": c, "STATUS": "MISSING_IN_SOURCE"})
            continue
        if trow is None:
            rows.append({"COLUMN_NAME": c, "STATUS": "MISSING_IN_TARGET"})
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
            sv = srow.get(norm_key, srow.get(raw_key))
            tv = trow.get(norm_key, trow.get(raw_key))
            if pd.isna(sv) and pd.isna(tv):
                continue
            if str(sv) != str(tv):
                diffs[raw_key] = {"source": sv, "target": tv}

        rows.append({"COLUMN_NAME": c, "STATUS": "MATCH" if not diffs else "DIFF", "DIFFS": diffs})

    return pd.DataFrame(rows)


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


def compare_keys(table, mysql_pk_df, mysql_uq_df, sr_parsed):
    m_pk = mysql_pk_list(mysql_pk_df, table)
    m_uq = mysql_unique_indexes(mysql_uq_df, table)

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


########################################


%run "./schema_compare_library"


# schema_compare_runner - Cell B2
# Purpose: choose any Source/Target env + DB combo.

dbutils.widgets.dropdown("Source Env", "QA", ["QA", "PPD-1", "PRD"])
dbutils.widgets.dropdown("Source DB", "MySQL", ["MySQL", "StarRocks"])

dbutils.widgets.dropdown("Target Env", "PRD", ["QA", "PPD-1", "PRD"])
dbutils.widgets.dropdown("Target DB", "StarRocks", ["MySQL", "StarRocks"])

dbutils.widgets.dropdown("Table Type", "Artifact", ["Artifact", "Input", "Output", "Staging"])
dbutils.widgets.dropdown("Debug Mode", "false", ["true", "false"])

source_env = dbutils.widgets.get("Source Env")
source_db  = dbutils.widgets.get("Source DB")
target_env = dbutils.widgets.get("Target Env")
target_db  = dbutils.widgets.get("Target DB")
table_type = dbutils.widgets.get("Table Type")
debug_mode = dbutils.widgets.get("Debug Mode").lower() == "true"

print("Source:", source_env, source_db)
print("Target:", target_env, target_db)
print("Table Type:", table_type)
print("Debug Mode:", debug_mode)


####################

# schema_compare_runner - Cell B3
# Purpose: load your connection functions and map env/db to callable.

# CHANGE THIS PATH to your connections notebook
%run "./all_connections_mysql_sr"

# ---- Map env to your EXACT function names ----
def get_mysql_runner(env: str):
    env = env.upper()
    if env == "QA":
        return mysqlConnection_qa
    if env == "PPD-1":
        return mysqlConnection_ppd_1
    if env == "PRD":
        return mysqlConnection_prd
    raise ValueError(f"Unknown MySQL env: {env}")

def get_starrocks_runner(env: str):
    env = env.upper()
    if env == "QA":
        return starrocksConnection_qa
    if env == "PPD-1":
        return starrocksConnection_ppd_1
    if env == "PRD":
        return starrocksConnection_prd
    raise ValueError(f"Unknown StarRocks env: {env}")

def get_runner(db: str, env: str):
    return get_mysql_runner(env) if db == "MySQL" else get_starrocks_runner(env)

run_source = get_runner(source_db, source_env)
run_target = get_runner(target_db, target_env)




###################


# schema_compare_runner - Cell B4

def resolve_mysql_schemas():
    return {
        "Artifact": "comp_engine_microservice",
        "Input":    "comp_engine_microservice",
        "Output":   "comp_engine_microservice_output",
        "Staging":  "comp_engine_microservice",
    }

def resolve_starrocks_schemas(env: str):
    e = env.lower()
    return {
        "Artifact": f"artifactsdb_{e}",
        "Input":    f"comp_engine_microservice_{e}",
        "Output":   f"comp_engine_microservice_output_{e}",
        "Staging":  f"stagedb_{e}",
    }

def get_side_schema(db: str, env: str, table_type: str) -> str:
    return resolve_mysql_schemas()[table_type] if db == "MySQL" else resolve_starrocks_schemas(env)[table_type]

source_schema = get_side_schema(source_db, source_env, table_type)
target_schema = get_side_schema(target_db, target_env, table_type)

print("Source schema:", source_schema)
print("Target schema:", target_schema)




######################



# schema_compare_runner - Cell B5
# Purpose: pick tables by category.

selection_tables = {
    "Artifact": get_artifact_tables(),
    "Input":    get_input_tables(),
    "Output":   get_output_tables(),
    "Staging":  get_staging_tables(),
}

reference_tables = selection_tables[table_type]
print("Num tables:", len(reference_tables))





##########################


# schema_compare_runner - Cell B6

IGNORE_COLUMNS = {"createdAt", "updatedAt"}



##########################


# schema_compare_runner - Cell B7 (DEBUG)

if debug_mode:
    sample_tables = reference_tables[:5]
    print("MySQL/Compared columns SQL sample:")
    print(MYSQL_COLUMNS_QUERY.format(schema=source_schema, tables=quote_list(sample_tables)))
    print(COMPARED_COLUMNS_QUERY.format(schema=target_schema, tables=quote_list(sample_tables)))



###########################


# schema_compare_runner - Cell B8

mysql_key = "mysql"
source_key = "mysql" if source_db == "MySQL" else "starrocks"
target_key = "mysql" if target_db == "MySQL" else "starrocks"

source_cols_raw = fetch_columns(
    schema=source_schema,
    tables=reference_tables,
    db_key=source_key,
    mysql_key=mysql_key,
    run_mysql=run_source,         # only used if source_key==mysql
    run_starrocks=run_source      # only used if source_key==starrocks
)

target_cols_raw = fetch_columns(
    schema=target_schema,
    tables=reference_tables,
    db_key=target_key,
    mysql_key=mysql_key,
    run_mysql=run_target,
    run_starrocks=run_target
)

source_cols = prepare_columns_df(source_cols_raw, "mysql" if source_db=="MySQL" else "starrocks")
target_cols = prepare_columns_df(target_cols_raw, "mysql" if target_db=="MySQL" else "starrocks")



#######################


# schema_compare_runner - Cell B9 (DEBUG)

if debug_mode and reference_tables:
    t0 = reference_tables[0]
    print("Sample table:", t0)
    display(source_cols[source_cols["TABLE_NAME"].str.lower()==t0.lower()])
    display(target_cols[target_cols["TABLE_NAME"].str.lower()==t0.lower()])



#####################


# schema_compare_runner - Cell B10

mysql_pk_df, mysql_uq_df = pd.DataFrame(), pd.DataFrame()
mysql_side = None

if source_db == "MySQL":
    mysql_side = "source"
    mysql_pk_df, mysql_uq_df = fetch_mysql_keys(source_schema, reference_tables, run_source)

elif target_db == "MySQL":
    mysql_side = "target"
    mysql_pk_df, mysql_uq_df = fetch_mysql_keys(target_schema, reference_tables, run_target)

# Spark → pandas if needed
if hasattr(mysql_pk_df, "toPandas") and not isinstance(mysql_pk_df, pd.DataFrame):
    mysql_pk_df = mysql_pk_df.toPandas()
if hasattr(mysql_uq_df, "toPandas") and not isinstance(mysql_uq_df, pd.DataFrame):
    mysql_uq_df = mysql_uq_df.toPandas()



######################


# schema_compare_runner - Cell B11

from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()

detail_results = {}
key_rows = []
summary_rows = []

for t in reference_tables:
    try:
        s_t = source_cols[source_cols["TABLE_NAME"].str.lower() == t.lower()]
        t_t = target_cols[target_cols["TABLE_NAME"].str.lower() == t.lower()]

        col_diff_df = compare_table_columns(s_t, t_t, IGNORE_COLUMNS)
        detail_results[t] = col_diff_df

        # ---- Keys ----
        if source_db == "StarRocks" and target_db == "StarRocks":
            ddl_s = fetch_starrocks_ddl(source_schema, t, run_source)
            ddl_t = fetch_starrocks_ddl(target_schema, t, run_target)

            sr_s = parse_starrocks_keys_from_ddl(ddl_s)
            sr_t = parse_starrocks_keys_from_ddl(ddl_t)

            key_rows.append({
                "TABLE_NAME": t,
                "SOURCE_SR_KEY_MODEL": sr_s["SR_KEY_MODEL"],
                "SOURCE_SR_KEY_COLUMNS": sr_s["SR_KEY_COLUMNS"],
                "SOURCE_SR_UNIQUE_COLUMNS": sr_s["SR_UNIQUE_COLUMNS"],
                "SOURCE_SR_ORDER_BY_COLUMNS": sr_s["SR_ORDER_BY_COLUMNS"],
                "TARGET_SR_KEY_MODEL": sr_t["SR_KEY_MODEL"],
                "TARGET_SR_KEY_COLUMNS": sr_t["SR_KEY_COLUMNS"],
                "TARGET_SR_UNIQUE_COLUMNS": sr_t["SR_UNIQUE_COLUMNS"],
                "TARGET_SR_ORDER_BY_COLUMNS": sr_t["SR_ORDER_BY_COLUMNS"],
                "KEY_MODEL_MATCH": sr_s["SR_KEY_MODEL"] == sr_t["SR_KEY_MODEL"],
                "KEY_COLUMNS_MATCH": sr_s["SR_KEY_COLUMNS"] == sr_t["SR_KEY_COLUMNS"],
                "UNIQUE_COLUMNS_MATCH": sr_s["SR_UNIQUE_COLUMNS"] == sr_t["SR_UNIQUE_COLUMNS"],
                "ORDER_BY_MATCH": sr_s["SR_ORDER_BY_COLUMNS"] == sr_t["SR_ORDER_BY_COLUMNS"],
            })

            pk_match = True
            uq_match = True
            key_model = f"{sr_s['SR_KEY_MODEL']} vs {sr_t['SR_KEY_MODEL']}"

        else:
            # MySQL ↔ StarRocks
            if source_db == "StarRocks":
                ddl = fetch_starrocks_ddl(source_schema, t, run_source)
                sr_parsed = parse_starrocks_keys_from_ddl(ddl)
            elif target_db == "StarRocks":
                ddl = fetch_starrocks_ddl(target_schema, t, run_target)
                sr_parsed = parse_starrocks_keys_from_ddl(ddl)
            else:
                sr_parsed = {"SR_KEY_MODEL":"N/A","SR_KEY_COLUMNS":[],"SR_UNIQUE_COLUMNS":[],"SR_ORDER_BY_COLUMNS":[]}

            key_diff = compare_keys(t, mysql_pk_df, mysql_uq_df, sr_parsed)
            key_rows.append({"TABLE_NAME": t, **key_diff})

            pk_match = key_diff["PK_MATCH"]
            uq_match = key_diff["UNIQUE_MATCH"]
            key_model = key_diff["SR_KEY_MODEL"]

        issues = col_diff_df[col_diff_df["STATUS"].isin(["DIFF","MISSING_IN_SOURCE","MISSING_IN_TARGET"])]
        summary_rows.append({
            "TABLE_NAME": t,
            "COLUMN_PASS": issues.empty,
            "NUM_COLUMN_ISSUES": int(len(issues)),
            "PK_MATCH": pk_match,
            "UNIQUE_MATCH": uq_match,
            "KEY_MODEL": key_model,
            "OVERALL_PASS": (issues.empty and pk_match and uq_match),
        })

    except Exception as e:
        print(f"[ERROR] Table={t} failed: {e}")
        if debug_mode and (source_db=="StarRocks" or target_db=="StarRocks"):
            try:
                if source_db=="StarRocks":
                    print(fetch_starrocks_ddl(source_schema, t, run_source))
                if target_db=="StarRocks":
                    print(fetch_starrocks_ddl(target_schema, t, run_target))
            except Exception:
                pass

        summary_rows.append({
            "TABLE_NAME": t,
            "COLUMN_PASS": False,
            "NUM_COLUMN_ISSUES": -1,
            "PK_MATCH": False,
            "UNIQUE_MATCH": False,
            "KEY_MODEL": "ERROR",
            "OVERALL_PASS": False,
            "ERROR": str(e),
        })

summary_df = pd.DataFrame(summary_rows).sort_values("TABLE_NAME")
keys_df = pd.DataFrame(key_rows).sort_values("TABLE_NAME")



#################


# schema_compare_runner - Cell B12

display(spark.createDataFrame(summary_df))
display(spark.createDataFrame(keys_df))




###################

# schema_compare_runner - Cell B13

for t, df in detail_results.items():
    print(f"\n===== {t} (Schema diff) =====")
    display(spark.createDataFrame(df))


