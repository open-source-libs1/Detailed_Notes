# Databricks notebook source
# ---------------------------------------
# Simple Parallel Runner for Validation Notebook
# ---------------------------------------

from concurrent.futures import ThreadPoolExecutor, as_completed

# Path of your existing validation notebook
TARGET_NOTEBOOK = "/Workspace/Shared/QA Test Automation/Validate_Input_Output_Tables_Final_Sai"

# Number of threads to use
MAX_THREADS = 8
TIMEOUT_SECS = 6 * 60 * 60   # 6 hours per notebook (optional safeguard)

# ---------------------------------------
# Define all input sets here
# ---------------------------------------
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
    # Add more inputs below as needed
    # {
    #     "Compare_Method": "Compare1",
    #     "Compared_DB": "MySQL",
    #     "Env": "QA",
    #     "Filter_By_Request": "No",
    #     "Scenario_ID": "XYZ123",
    #     "Table_Type": "Output",
    #     "UW_Req_ID": "REQ456",
    # },
]

# ---------------------------------------
# Helper function to execute notebook
# ---------------------------------------
def _run_notebook(params):
    try:
        dbutils.notebook.run(TARGET_NOTEBOOK, TIMEOUT_SECS, params)
        print(f"✅ Completed: {params.get('Scenario_ID')} | {params.get('UW_Req_ID')}")
    except Exception as e:
        print(f"❌ Failed: {params.get('Scenario_ID')} | {params.get('UW_Req_ID')} | Error: {e}")

# ---------------------------------------
# Parallel Execution
# ---------------------------------------
print(f"Executing {len(RUN_INPUTS)} notebooks in parallel (max {MAX_THREADS})...")

with ThreadPoolExecutor(max_workers=min(MAX_THREADS, len(RUN_INPUTS))) as executor:
    futures = [executor.submit(_run_notebook, params) for params in RUN_INPUTS]
    for _ in as_completed(futures):
        pass  # no result collection

print("✅ All notebook executions submitted.")
