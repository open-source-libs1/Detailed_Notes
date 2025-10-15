# Databricks notebook source
# ---------------------------
# Synchronous Runner (sequential, no result collection)
# ---------------------------
import time
import json

TARGET_NOTEBOOK = "/Workspace/Shared/QA Test Automation/Validate_Input_Output_Tables_Final_Sai"
TIMEOUT_SECS    = 6 * 60 * 60   # per run
RETRIES         = 1             # additional attempts per input (0 = no retry)
SLEEP_BETWEEN_S = 3             # pause between runs

RUN_INPUTS = [
    {
        "Compare_Method": "Compare2",
        "Compared_DB": "StarRocks",
        "Env": "QA",
        "Filter_By_Request": "Yes",
        "Scenario_ID": "2F59464FB5664723B16D1FD2",
        "Table_Type": "Input",
        "UW_Req_ID": "EFF46DD7B6384048A58A9786",
    },
    # add more dicts...
]

def _to_widget_str(v):
    if v is None: return ""
    if isinstance(v, bool): return "true" if v else "false"
    return str(v)

def _coerce_params(d):  # widgets expect strings
    return {k: _to_widget_str(v) for k, v in d.items()}

failures = []

for idx, params in enumerate(RUN_INPUTS, 1):
    p = _coerce_params(params)
    tag = f"{p.get('Scenario_ID','')}/{p.get('UW_Req_ID','')}/{p.get('Compared_DB','')}/{p.get('Table_Type','')}"
    attempt = 0
    while True:
        attempt += 1
        print(f"[{idx}/{len(RUN_INPUTS)}] Running {tag} (attempt {attempt}) ...")
        try:
            dbutils.notebook.run(TARGET_NOTEBOOK, TIMEOUT_SECS, p)
            print(f"✅ Done {tag}")
            break
        except Exception as e:
            print(f"❌ Failed {tag}: {e}")
            if attempt > RETRIES:
                failures.append({"params": params, "error": repr(e)})
                break
            time.sleep(5)  # brief backoff before retry
    time.sleep(SLEEP_BETWEEN_S)

if failures:
    print(f"Completed with {len(failures)} failure(s). See list below:")
    for f in failures:
        print(json.dumps(f, ensure_ascii=False))
else:
    print("✅ All runs completed successfully.")
