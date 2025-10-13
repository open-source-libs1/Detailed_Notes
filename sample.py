for col in round_cols_rev:
    if col in mysql_pd.columns:
        mysql_pd[col] = mysql_pd[col].apply(lambda x: round(x, -1) if isinstance(x, (int, float)) else x)

for col in round_cols_rev:
    if col in starrocks_pd.columns:
        starrocks_pd[col] = starrocks_pd[col].apply(lambda x: round(x, -1) if isinstance(x, (int, float)) else x)
