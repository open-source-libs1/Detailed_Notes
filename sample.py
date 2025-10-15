# --- CONFIG: edit these two paths only ---
workspace_dir = "/Workspace/Shared/QA Test Automation/Star Rocks Migration/Validate_Table_Output"
abfss_base   = "abfss://gold@sapbmuscafpdatalakeqa.dfs.core.windows.net/compengine/tmp"
# ----------------------------------------

export_results = True

if export_results:
    output_name = f"{table_type}_accuracy_F1A1F763C59542998D7BA67110BE99BA"  # you already set this
    ts = time_stamp()  # your existing helper
    base = f"{output_name}{environment}_{ts}"
    fname = f"{base}.xlsx"

    # 1) Write the Excel ONCE to a temp DBFS path
    tmp_dir  = "dbfs:/tmp"
    tmp_path = f"{tmp_dir}/{fname}"
    write_df_multiple_to_excel(tmp_path, reference_table_result_dfs)  # <== note: full path, not folder+name

    # Get size to decide Workspace copy
    import os
    size_bytes = os.path.getsize(f"/dbfs/tmp/{fname}")
    limit = 10 * 1024 * 1024  # 10 MB Workspace export cap

    # 2) Copy to Workspace (only if small enough)
    try:
        if size_bytes <= limit:
            dbutils.fs.mkdirs(workspace_dir)
            dbutils.fs.cp(tmp_path, f"{workspace_dir}/{fname}", True)
            print(f"✅ Saved to Workspace: {workspace_dir}/{fname}")
        else:
            print(f"⚠️ Skipped Workspace copy ({size_bytes} bytes > 10 MB limit).")
    except Exception as e:
        print(f"⚠️ Workspace copy failed: {e}")

    # 3) Copy to ADLS Gen2 (ABFSS) — always
    abfss_dir = f"{abfss_base}/{base}"
    try:
        dbutils.fs.mkdirs(abfss_dir)
        dbutils.fs.cp(tmp_path, f"{abfss_dir}/{fname}", True)
        print(f"✅ Saved to ADLS: {abfss_dir}/{fname}")
    except Exception as e:
        print(f"❌ ADLS copy failed: {e}")

    # 4) (Optional but handy) put a download-friendly copy in /FileStore
    #    This avoids the Workspace 10 MB limit and gives you a URL.
    try:
        fs_dir = "dbfs:/FileStore/exports"
        dbutils.fs.mkdirs(fs_dir)
        dbutils.fs.cp(tmp_path, f"{fs_dir}/{fname}", True)

        # Build a browser URL automatically
        try:
            host = dbutils.notebook.entry_point.getDbutils().notebook().getContext().browserHostName().get()
            print(f"🔗 Download: https://{host}/files/exports/{fname}")
        except:
            print(f"🔗 Download (append your host): /files/exports/{fname}")
    except Exception as e:
        print(f"⚠️ FileStore copy failed: {e}")

else:
    print("Skipping export")
