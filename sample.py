for name, df in [
    ("rebate_conventional_df", rebate_conventional_df),
    ("starrocks_rebate_df", starrocks_rebate_df),
    ("compared_rebate_df", compared_rebate_df),
]:
    print(f"{name}: {type(df)}")
