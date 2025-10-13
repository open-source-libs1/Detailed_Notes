import pandas as pd
import numpy as np

def normalize_keys(df: pd.DataFrame, keys, mode="auto"):
    """
    Make key columns the same dtype across frames.
    mode="int"  -> force nullable Int64 (fails to coerce to NaN if not numeric)
    mode="str"  -> force strings (preserves leading zeros)
    mode="auto" -> try Int64 on both frames; if any non-numeric exists, fallback to str
    """
    keys = [c for c in keys if c in df.columns]
    if mode == "int":
        for c in keys:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        return df
    if mode == "str":
        for c in keys:
            df[c] = (df[c].astype(str)
                           .str.strip()
                           .str.replace("\u00a0", " ", regex=False)  # non-breaking space
                           .str.replace(r"\.0+$", "", regex=True))  # strip .0 from csv
        # optional: treat missing keys uniformly
        df[keys] = df[keys].fillna("")  # or "<<NULL>>"
        return df
    raise ValueError("mode must be 'int' or 'str'")

# --- Choose ONE of these normalizations for BOTH frames ---
# 1) If IDs must be numeric (no leading zeros matter):
for d in (mysql_pd, starrocks_pd):
    normalize_keys(d, key_cols, mode="int")

# 2) If IDs may be alphanumeric or leading zeros matter, use strings instead:
# for d in (mysql_pd, starrocks_pd):
#     normalize_keys(d, key_cols, mode="str")
