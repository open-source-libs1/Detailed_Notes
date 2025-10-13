

import pandas as pd
import numpy as np

def safe_round(df, cols, places=-1):
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return df
    # optional: strip commas/whitespace if numbers arrive as strings
    df[cols] = (df[cols].apply(lambda s: pd.to_numeric(
                        s.astype(str).str.replace(',', '', regex=False).str.strip(),
                        errors='coerce'))
                        .round(places))
    return df

mysql_pd     = safe_round(mysql_pd, round_cols_rev, -1)
starrocks_pd = safe_round(starrocks_pd, round_cols_rev, -1)

# (optional) make nicer dtypes
mysql_pd[round_cols_rev]     = mysql_pd[round_cols_rev].convert_dtypes()
starrocks_pd[round_cols_rev] = starrocks_pd[round_cols_rev].convert_dtypes()
