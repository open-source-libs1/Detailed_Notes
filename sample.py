# 1) Convert Spark DFs -> pandas (Comparison is already pandas)
df_dict = {
    "Conventional": rebate_conventional_df.toPandas(),
    "TC": starrocks_rebate_df.toPandas(),
    "Comparison": compared_rebate_df,  # already pandas
}

# 2) Call your existing function (write to Workspace path via /dbfs mirror)
export_file_name = f"Rebate_Conv_vs_TC_{uw_req_id}_{time_stamp()}.xlsx"
export_path = "/dbfs/Workspace/Shared/QA Test Automation/True Cost/Rebate_Validation_Output"

write_df_multiple_to_excel(export_file_name, export_path, df_dict)
