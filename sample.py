# Databricks notebook source
# Parallel fan-out: one thread per notebook; sequential per-notebook across param triples.
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal
import json, threading

# ---- Inputs you already have -------------------------------------------------
# notebook_paths_nc: List[str]     # notebooks to call
# non_coalition_list: List[Tuple[scenario_id, lob_id, uw_req_id]]
# return_str_lob: Callable[[Any], str]  # your existing helper

# ---- Concurrency knobs -------------------------------------------------------
MAX_THREADS   = min(len(notebook_paths_nc), 8)      # cap threads
TIMEOUT_SECS  = 6 * 60 * 60                         # generous timeout for each run

# ---- Run context / shared log ------------------------------------------------
run_user = dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get()
run_id   = int(datetime.now().strftime("%Y%m%d%H%M%S"))
log_data = []                # list of dicts (same as your current design)
_log_lock = threading.Lock() # protects log_data

# ---- De-duplicate triples ----------------------------------------------------
unique_triples = list({(sid, lob, uw) for (sid, lob, uw) in non_coalition_list})

# ---- Helpers -----------------------------------------------------------------
def _read_output_as_spark_df(path: str):
    """
    Your called notebook returns a location in `output`.
    Try Delta first, then Parquet fallback, then CSV as last resort.
    """
    try:
        return spark.read.format("delta").load(path)
    except Exception:
        try:
            return spark.read.parquet(path)
        except Exception:
            try:
                return spark.read.csv(path, header=True, inferSchema=True)
            except Exception:
                return None

def _append_records_to_log(
    *,
    records: list[dict],
    notebook_path: str,
    scenario_id,
    lob_id,
    uw_req_id,
    status: str,
    start_time: datetime,
    end_time: datetime,
    output_path: str | None,
    error_repr: str | None
):
    """Enrich each record with your metadata and push to shared log_data."""
    lob_name = return_str_lob(lob_id)
    duration = (end_time - start_time).total_seconds()
    est_ctg  = notebook_path.split("/")[-1]  # mimic your IS_CTG derivation

    enriched = []
    for rec in (records or [{}]):  # if no rows, still write one summary row
        rec = dict(rec)  # copy to avoid mutating Pandas-derived dict
        rec["lob"]              = lob_name
        rec["run_id"]           = run_id
        rec["start_time"]       = start_time.isoformat()
        rec["end_time"]         = end_time.isoformat()
        rec["duration"]         = duration
        rec["IS_CTG"]           = est_ctg
        rec["EXECUTION_STATUS"] = status
        rec["REQUEST_ID"]       = "NA"
        rec["TASK_ID"]          = "NA"
        rec["RUN_USER"]         = run_user
        rec["PARENT_REQUEST_ID"]= uw_req_id
        rec["APP_ID"]           = scenario_id
        rec["notebook"]         = notebook_path
        rec["output_path"]      = output_path
        rec["error"]            = error_repr
        enriched.append(rec)

    with _log_lock:
        log_data.extend(enriched)

def _spark_df_to_records(df):
    """
    Your current pipeline: Spark -> Pandas -> Decimal-safe dict(records).
    """
    if df is None:
        return []

    pdf = df.toPandas()
    # Convert Decimal to float safely (mimics your applymap + to_dict('records'))
    safe_pdf = pdf.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
    return json.loads(json.dumps(safe_pdf.to_dict(orient="records")))

# ---- Core worker: runs one notebook for one triple --------------------------
def run_one_invocation(notebook_path: str, triple):
    scenario_id, lob_id, uw_req_id = triple
    params = {
        "scenario_id": scenario_id,
        "lob":         lob_id,
        "uw_req_id":   uw_req_id,
        "run_id":      run_id,
    }

    start = datetime.utcnow()
    status = "COMPLETED"
    output_path = None
    err = None

    try:
        # This returns the output string from the child notebook (e.g., a path)
        output_path = dbutils.notebook.run(notebook_path, TIMEOUT_SECS, params)
        df = _read_output_as_spark_df(output_path)
        records = _spark_df_to_records(df)
    except Exception as e:
        status = "FAILED"
        err = repr(e)
        records = []  # still log a row with error & metadata

    end = datetime.utcnow()
    _append_records_to_log(
        records=records,
        notebook_path=notebook_path,
        scenario_id=scenario_id,
        lob_id=lob_id,
        uw_req_id=uw_req_id,
        status=status,
        start_time=start,
        end_time=end,
        output_path=output_path,
        error_repr=err,
    )

# ---- Per-notebook worker: sequential over triples for that notebook ---------
def per_notebook_worker(notebook_path: str, triples):
    for t in triples:
        run_one_invocation(notebook_path, t)

# ---- Fan-out: one thread per notebook ---------------------------------------
with ThreadPoolExecutor(max_workers=MAX_THREADS) as pool:
    futs = [pool.submit(per_notebook_worker, nb, unique_triples) for nb in notebook_paths_nc]
    for f in as_completed(futs):
        # Exceptions already captured per invocation, but catch worker-level issues too.
        try:
            f.result()
        except Exception as e:
            print(f"[Worker crashed] {e!r}")

# ---- Done: log_data now mirrors your current structure, across all runs -----
print(f"Parallel run complete: {len(log_data)} records written; run_id={run_id}")
display(spark.createDataFrame(log_data))
