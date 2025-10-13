
import numpy as np

for col in round_cols_rev:
    mysql_pd[col] = mysql_pd[col].apply(lambda x: round(x, -1) if pd.notnull(x) else np.nan)
    starrocks_pd[col] = starrocks_pd[col].apply(lambda x: round(x, -1) if pd.notnull(x) else np.nan)
