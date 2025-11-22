# Cell B2
# Pick any Source/Target env + DB combo.

dbutils.widgets.dropdown("Source Env", "qa", ["qa", "ppd1", "prd"])
dbutils.widgets.dropdown("Source DB", "mysql", ["mysql", "starrocks"])

dbutils.widgets.dropdown("Target Env", "prd", ["qa", "ppd1", "prd"])
dbutils.widgets.dropdown("Target DB", "starrocks", ["mysql", "starrocks"])

dbutils.widgets.dropdown("Table Type", "Artifact", ["Artifact", "Input", "Output", "Staging"])
dbutils.widgets.dropdown("Debug Mode", "false", ["true", "false"])

source_env = dbutils.widgets.get("Source Env").lower()
source_db  = dbutils.widgets.get("Source DB").lower()
target_env = dbutils.widgets.get("Target Env").lower()
target_db  = dbutils.widgets.get("Target DB").lower()

table_type = dbutils.widgets.get("Table Type")
debug_mode = dbutils.widgets.get("Debug Mode").lower() == "true"

print("Source:", source_env, source_db)
print("Target:", target_env, target_db)
print("Table Type:", table_type)
print("Debug Mode:", debug_mode)



###############################


# Cell B3
# Load your actual connections notebook.
# Update path below to your real connections notebook.

%run "./all_connections_mysql_sr"

# ---- map env -> env-specific connection functions ----
# THESE NAMES MUST MATCH WHAT EXISTS IN your connections notebook.

MYSQL_CONN_BY_ENV = {
    "qa":   mysqlConnection_qa,
    "ppd1": mysqlConnection_ppd1,
    "prd":  mysqlConnection_prd,
}

STARROCKS_CONN_BY_ENV = {
    "qa":   starrocksConnection_qa,
    "ppd1": starrocksConnection_ppd1,
    "prd":  starrocksConnection_prd,
}

def get_env_conn(db: str, env: str):
    """
    Returns the raw connection function for a given db/env.
    Raw function signature: fn(database_name, query) -> Spark DF
    """
    env = env.lower()
    if db == "mysql":
        if env not in MYSQL_CONN_BY_ENV:
            raise ValueError(f"MySQL env not supported: {env}")
        return MYSQL_CONN_BY_ENV[env]

    if db == "starrocks":
        if env not in STARROCKS_CONN_BY_ENV:
            raise ValueError(f"StarRocks env not supported: {env}")
        return STARROCKS_CONN_BY_ENV[env]

    raise ValueError(f"Unknown db: {db}")


def make_runner(db: str, env: str):
    """
    Wrap raw env/db connection to a standard callable:
        run(schema, query) -> Spark DF
    Ensures schema is passed through AND environment stays lowercase usage.
    """
    raw_fn = get_env_conn(db, env)

    def _run(schema: str, query: str):
        # schema/database_name should be passed as-is (already resolved)
        return raw_fn(schema, query)

    return _run


run_source = make_runner(source_db, source_env)
run_target = make_runner(target_db, target_env)

print("Connection mapping OK")



###########################


# Cell B4
# Schema naming rules per DB and env.

def resolve_mysql_schemas():
    # MySQL schemas don't vary by env in your setup
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
    env = env.lower()
    if db == "mysql":
        return resolve_mysql_schemas()[table_type]
    return resolve_starrocks_schemas(env)[table_type]

source_schema = get_side_schema(source_db, source_env, table_type)
target_schema = get_side_schema(target_db, target_env, table_type)

print("Source schema:", source_schema)
print("Target schema:", target_schema)




#########################



# Cell B5
# Your existing helpers must exist.

selection_tables = {
    "Artifact": get_artifact_tables(),
    "Input":    get_input_tables(),
    "Output":   get_output_tables(),
    "Staging":  get_staging_tables(),
}

reference_tables = selection_tables[table_type]
print("Num tables:", len(reference_tables))




#########################


# Cell B6

IGNORE_COLUMNS = {"createdAt", "updatedAt"}  # add more if needed



###########################


# Cell B7 (DEBUG)

if debug_mode and reference_tables:
    sample_tables = reference_tables[:5]
    print("Source columns SQL sample:")
    print(MYSQL_COLUMNS_QUERY.format(schema=source_schema, tables=quote_list(sample_tables)))
    print("\nTarget columns SQL sample:")
    print(COMPARED_COLUMNS_QUERY.format(schema=target_schema, tables=quote_list(sample_tables)))



#################################


# Cell B8
# Fetch schema for both sides via env-specific connections.

mysql_key = "mysql"
source_key = "mysql" if source_db == "mysql" else "starrocks"
target_key = "mysql" if target_db == "mysql" else "starrocks"

source_cols_raw = fetch_columns(
    schema=source_schema,
    tables=reference_tables,
    db_key=source_key,
    mysql_key=mysql_key,
    run_mysql=run_source,
    run_starrocks=run_source
)

target_cols_raw = fetch_columns(
    schema=target_schema,
    tables=reference_tables,
    db_key=target_key,
    mysql_key=mysql_key,
    run_mysql=run_target,
    run_starrocks=run_target
)

source_cols = prepare_columns_df(source_cols_raw, "mysql" if source_db=="mysql" else "starrocks")
target_cols = prepare_columns_df(target_cols_raw, "mysql" if target_db=="mysql" else "starrocks")




######################


# Cell B9 (DEBUG)

if debug_mode and reference_tables:
    t0 = reference_tables[0]
    print("Sample table:", t0)
    display(source_cols[source_cols["TABLE_NAME"].str.lower()==t0.lower()])
    display(target_cols[target_cols["TABLE_NAME"].str.lower()==t0.lower()])




#########################


# Cell B10

mysql_pk_df, mysql_uq_df = pd.DataFrame(), pd.DataFrame()

if source_db == "mysql":
    mysql_pk_df, mysql_uq_df = fetch_mysql_keys(source_schema, reference_tables, run_source)

elif target_db == "mysql":
    mysql_pk_df, mysql_uq_df = fetch_mysql_keys(target_schema, reference_tables, run_target)

# Convert Spark -> pandas if needed
if hasattr(mysql_pk_df, "toPandas") and not isinstance(mysql_pk_df, pd.DataFrame):
    mysql_pk_df = mysql_pk_df.toPandas()
if hasattr(mysql_uq_df, "toPandas") and not isinstance(mysql_uq_df, pd.DataFrame):
    mysql_uq_df = mysql_uq_df.toPandas()





########################



# Cell B11

from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()

detail_results = {}
key_rows = []
summary_rows = []

for t in reference_tables:
    try:
        s_t = source_cols[source_cols["TABLE_NAME"].str.lower() == t.lower()]
        t_t = target_cols[target_cols["TABLE_NAME"].str.lower() == t.lower()]

        # Column compare
        col_diff_df = compare_table_columns(s_t, t_t, IGNORE_COLUMNS)
        detail_results[t] = col_diff_df

        # --- Key compare ---
        if source_db == "starrocks" and target_db == "starrocks":
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
            if source_db == "starrocks":
                ddl = fetch_starrocks_ddl(source_schema, t, run_source)
                sr_parsed = parse_starrocks_keys_from_ddl(ddl)
            elif target_db == "starrocks":
                ddl = fetch_starrocks_ddl(target_schema, t, run_target)
                sr_parsed = parse_starrocks_keys_from_ddl(ddl)
            else:
                sr_parsed = {
                    "SR_KEY_MODEL":"N/A","SR_KEY_COLUMNS":[],"SR_UNIQUE_COLUMNS":[],"SR_ORDER_BY_COLUMNS":[]
                }

            key_diff = compare_keys(t, mysql_pk_df, mysql_uq_df, sr_parsed)
            key_rows.append({"TABLE_NAME": t, **key_diff})

            pk_match = key_diff["PK_MATCH"]
            uq_match = key_diff["UNIQUE_MATCH"]
            key_model = key_diff["SR_KEY_MODEL"]

        # Summary
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

        # Quick DDL print in debug mode
        if debug_mode and (source_db=="starrocks" or target_db=="starrocks"):
            try:
                if source_db=="starrocks":
                    print(fetch_starrocks_ddl(source_schema, t, run_source))
                if target_db=="starrocks":
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




####################


# Cell B12

display(spark.createDataFrame(summary_df))
display(spark.createDataFrame(keys_df))




###############

# Cell B13

for t, df in detail_results.items():
    print(f"\n===== {t} (Schema diff) =====")
    display(spark.createDataFrame(df))


