# --- Imports ---
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal
import json

# --- Assumes these exist from your context ---
# MAX_THREADS, TIMEOUT_SECS, _log_lock, unique_triples
# notebook_path_nc (list of notebook paths)
# non_coalition_list (list of (scenario_id, lob_id, uw_req_id))
# return_str_lob(lob_id)  -> str
# dbutils, spark available in the Databricks runtime

# If you prefer: MAX_THREADS = min(len(notebook_path_nc), 12)

run_user = dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get()
run_id = int(datetime.now().strftime("%d%m%Y%H%M%S"))

# Shared result, same type as before
log_data = []

def _run_single_notebook(scenario_id: int, lob_id: int, uw_req_id: int, notebook_path: str) -> list[dict]:
    """
    Executes one notebook and returns a list of dicts to be appended to log_data.
    Mirrors the old behavior/fields exactly. On failure, returns [] (old code only printed errors).
    """
    try:
        print(f"Running notebook for scenario_id = {scenario_id}, lob = {lob_id}, uw_req_id = {uw_req_id}")
        notebook_params = {
            "scenario_id": scenario_id,
            "lob": lob_id,
            "uw_req_id": uw_req_id,
            "run_id": run_id,
        }

        print("Non_Coalition_loop")
        start_time = datetime.utcnow()
        # Use provided TIMEOUT_SECS to be consistent with your new config
        output = dbutils.notebook.run(notebook_path, TIMEOUT_SECS, notebook_params)
        notebook_status = "COMPLETED"
        end_time = datetime.utcnow()
        duration_sec = (end_time - start_time).total_seconds()
        lob_name = return_str_lob(lob_id)

        # Keep your exact load/convert pattern (Delta -> pandas -> dicts) and Decimal->float conversion
        temp_data = spark.read.format("delta").load(output)
        df_conversion = (
            temp_data.toPandas()
            .applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
            .to_dict(orient="records")
        )
        json_dump = json.dumps(df_conversion)
        list_of_dictionaries = json.loads(json_dump)

        # Add the same metadata keys/values you currently add
        for metadat_insert in list_of_dictionaries:
            metadat_insert["lob"] = lob_name
            metadat_insert["run_id"] = run_id
            metadat_insert["start_time"] = start_time.isoformat()
            metadat_insert["end_time"] = end_time.isoformat()
            metadat_insert["duration"] = duration_sec
            metadat_insert["TS_CTG"] = notebook_path.split("/")[-1]
            metadat_insert["EXECUTION_STATUS"] = notebook_status
            metadat_insert["REQUEST_ID"] = "NA"
            metadat_insert["TASK_ID"] = "NA"
            metadat_insert["RUN_USER"] = run_user
            metadat_insert["PARENT_REQUEST_ID"] = uw_req_id
            metadat_insert["APP_ID"] = scenario_id

        print(f"scenario_id {scenario_id}  lob {lob_name}  uw_req_id {uw_req_id}  run_id = {run_id}")
        print(notebook_path)
        print("Non_Coalition_loop_ends")
        print("\n\n", output)

        return list_of_dictionaries

    except Exception as e:
        # Preserve old behavior: log/print, do not append any result rows on failure
        print(f"Error running notebook: {e}")
        return []


# ----------------- Parallel Orchestration -----------------
# Build all tasks across unique triples × all notebooks
tasks = []
for (scenario_id, lob_id, uw_req_id) in unique_triples:
    for notebook_path in notebook_path_nc:
        tasks.append((scenario_id, lob_id, uw_req_id, notebook_path))

# Run with a bounded thread-pool
# Note: Spark & dbutils calls are made inside worker threads; Databricks supports this pattern for notebook runs.
with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
    futures = {
        executor.submit(_run_single_notebook, sid, lob, uw, npath): (sid, lob, uw, npath)
        for (sid, lob, uw, npath) in tasks
    }

    for future in as_completed(futures):
        result_rows = future.result()  # always a list (possibly empty)
        if result_rows:
            # Keep log_data identical to old structure; extend under a lock for safety
            with _log_lock:
                log_data.extend(result_rows)

# At this point, log_data has exactly the same structure/content shape you produced before.
# If your old cell relied on the variable existing (not function return), we simply leave it bound:
# log_data  # <- same list[dict] as before
