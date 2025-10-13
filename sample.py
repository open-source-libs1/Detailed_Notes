


import pandas as pd

mysql_pd     = mysql_df.toPandas()
starrocks_pd = starrocks_df.toPandas()

# ensure it's a list even if a single column name was passed
if isinstance(round_cols_rev, str):
    round_cols_rev = [round_cols_rev]

def _coerce_numeric(s: pd.Series) -> pd.Series:
    # remove thousands separators and trim spaces without using .str
    s = s.replace({',': ''}, regex=True)               # leaves numerics untouched
    s = s.replace(r'^\s+|\s+$', '', regex=True)        # strip leading/trailing spaces
    return pd.to_numeric(s, errors='coerce')           # non-numeric -> NaN

# make columns numeric and round to nearest 10 (NaNs are ignored by round)
mysql_pd[round_cols_rev] = mysql_pd[round_cols_rev].apply(_coerce_numeric).round(-1)
starrocks_pd[round_cols_rev] = starrocks_pd[round_cols_rev].apply(_coerce_numeric).round(-1)
