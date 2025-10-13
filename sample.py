import pandas as pd

# Convert Spark -> Pandas
mysql_pd = mysql_df.toPandas()
starrocks_pd = starrocks_df.toPandas()

# Ensure the list of columns is a list (in case a single string was passed)
if isinstance(round_cols_rev, str):
    round_cols_rev = [round_cols_rev]

# Helper: coerce to numeric (handles strings like "12.3", " 1,234 ", "", None)
def _coerce_numeric(s: pd.Series) -> pd.Series:
    if s.dtype == "O":  # object -> likely strings
        s = s.str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce")   # non-numeric -> NaN

# Make columns numeric and round to nearest 10 (ignores NaN safely)
mysql_pd[round_cols_rev] = (
    mysql_pd[round_cols_rev].apply(_coerce_numeric).round(-1)
)
starrocks_pd[round_cols_rev] = (
    starrocks_pd[round_cols_rev].apply(_coerce_numeric).round(-1)
)
