import pandas as pd
from functools import reduce

# ----------------------------
# Helpers
# ----------------------------
def _to_pandas(df):
    """Normalize output from starrocksConnection_qa() to pandas DataFrame."""
    if df is None:
        return None
    # Spark DF has toPandas()
    if hasattr(df, "toPandas"):
        return df.toPandas()
    return df

def _is_empty(df):
    if df is None:
        return True
    # pandas
    if isinstance(df, pd.DataFrame):
        return df.empty
    # spark or unknown
    try:
        return df is None
    except Exception:
        return True

def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def _safe_bool01(x):
    # handles True/False, "true"/"false", 1/0, "1"/"0"
    if isinstance(x, bool):
        return 1 if x else 0
    if x is None:
        return 0
    s = str(x).strip().lower()
    if s in ("true", "t", "yes", "y", "1"):
        return 1
    if s in ("false", "f", "no", "n", "0"):
        return 0
    try:
        return 1 if int(x) != 0 else 0
    except Exception:
        return 0

def _channel_label(k):
    m = {1: "Retail", 2: "Mail", 3: "Specialty", 4: "SRx at Retail"}
    return m.get(_safe_int(k, -1), "NA")

def _brand_label(k):
    # from your SQL: when 1 then "Generic" else "Brand"
    return "Generic" if _safe_int(k, 0) == 1 else "Brand"

def _chunked(iterable, size=800):
    lst = list(iterable)
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

# ----------------------------
# Main logic
# ----------------------------
All_Revenue_Combined_NPGs = []
_rev_dfs = []
_all_network_ids = set()

for pg in rev_base_dict:
    # proj_year as int
    year = _safe_int(pg.get("proj_year"), 0)

    # constants (do NOT depend on revenue columns)
    brand_generic_txt = _brand_label(pg.get("brand_generic_key"))
    channel_txt       = _channel_label(pg.get("srx_arrangement_key"))
    days_supply_01    = _safe_bool01(pg.get("days_supply_key"))

    # Revenue query ONLY (no artifacts join, no GROUP BY — we aggregate later if needed)
    # Note: keep filters exactly like your working COUNT query.
    revenue_q = f"""
    SELECT
        rs.uw_req_id,
        rs.network_pricing_group_id,
        rs.rebate_pricing_group_id,
        rs.srx_pricing_group_id,
        rs.proj_year,
        rs.proj_network_id,
        rs.primary_ntwrk_id,
        rs.secondary_ntwrk_id,
        rs.tertiary_ntwrk_id,
        rs.network_guid,
        rs.formulary_guid,

        rs.mc,
        rs.cstm_ntwk_ind,
        rs.cop_ind,

        rs.cp_fin_sc_id,
        rs.price_type_id,
        rs.network_pref_ind_id,
        rs.pharmacy_capped_noncapped_id,

        rs.tag_paper_claims,
        rs.tag_340b,
        rs.tag_340b_clm,
        rs.tag_340b_pharm,
        rs.tag_coordination_of_benefits,

        rs.num_claims,
        rs.awp_total,
        rs.acquisition_cost,
        rs.cogs_trad_pbm_total,
        rs.cogs_trans_pbm_total,
        rs.cogs_dispns_fee_trad_pbm_total,
        rs.cogs_dispns_fee_trans_pbm_total,
        rs.cogs_trad_medi_total,
        rs.cogs_trans_medi_total,
        rs.cogs_dispns_fee_trad_medi_total,
        rs.cogs_dispns_fee_trans_medi_total,

        rs.mac_list_1,
        rs.mac_list_2,
        rs.mac_list_3,
        rs.mac_list_4,
        rs.mac_list_5,
        rs.mac_list_6,
        rs.mac_list_7,
        rs.mac_list_8,
        rs.mac_list_9,
        rs.mac_list_10

    FROM comp_engine_microservice_qa.revenue rs
    WHERE rs.uw_req_id = '{pg["uw_req_id"]}'
      AND rs.proj_year = {year}
      AND rs.network_pricing_group_id = '{pg["network_pricing_group_id"]}'
      AND rs.rebate_pricing_group_id  = '{pg["rebate_pricing_group_id"]}'
      AND rs.srx_pricing_group_id     = '{pg["srx_pricing_group_id"]}'
      AND rs.network_guid             = '{pg["network_guid"]}'
      AND rs.formulary_guid           = '{pg["formulary_guid"]}'
    """

    try:
        rev_df = starrocksConnection_qa("comp_engine_microservice_qa", revenue_q)
        rev_df = _to_pandas(rev_df)
    except Exception as e:
        print(f"[WARN] Revenue query failed for uw_req_id={pg.get('uw_req_id')} year={year}: {e}")
        rev_df = None

    if _is_empty(rev_df):
        # keep alignment
        _rev_dfs.append(pd.DataFrame())
        continue

    # Add constant columns (replaces your SQL CASE using pg[...] values)
    rev_df["Brand_Generic"] = brand_generic_txt
    rev_df["Channel"] = channel_txt
    rev_df["days_supply"] = days_supply_01

    # Collect ids for artifacts lookup
    for col in ["proj_network_id", "primary_ntwrk_id", "secondary_ntwrk_id"]:
        if col in rev_df.columns:
            _all_network_ids.update(pd.to_numeric(rev_df[col], errors="coerce").dropna().astype(int).tolist())

    _rev_dfs.append(rev_df)

# ----------------------------
# Query artifactsdb_qa.network separately and merge
# ----------------------------
net_df = pd.DataFrame(columns=["id", "title"])

if len(_all_network_ids) > 0:
    net_parts = []
    for chunk in _chunked(_all_network_ids, size=800):  # keep IN list safe
        ids_csv = ",".join(str(i) for i in chunk)
        net_q = f"""
        SELECT id, title
        FROM artifactsdb_qa.network
        WHERE id IN ({ids_csv})
        """
        try:
            part = starrocksConnection_qa("artifactsdb_qa", net_q)
            part = _to_pandas(part)
            if part is not None and not part.empty:
                net_parts.append(part)
        except Exception as e:
            print(f"[WARN] Artifacts query failed for chunk: {e}")

    if net_parts:
        net_df = pd.concat(net_parts, ignore_index=True).drop_duplicates(subset=["id"])

# Build mapping DFs (same pattern you were doing)
if not net_df.empty:
    net_df["id"] = pd.to_numeric(net_df["id"], errors="coerce").astype("Int64")
    proj_map = net_df.rename(columns={"id": "proj_network_id", "title": "projected_network"})
    prim_map = net_df.rename(columns={"id": "primary_ntwrk_id", "title": "primary_network"})
    sec_map  = net_df.rename(columns={"id": "secondary_ntwrk_id", "title": "secondary_network"})
else:
    proj_map = pd.DataFrame(columns=["proj_network_id", "projected_network"])
    prim_map = pd.DataFrame(columns=["primary_ntwrk_id", "primary_network"])
    sec_map  = pd.DataFrame(columns=["secondary_ntwrk_id", "secondary_network"])

# Merge and finalize output list
All_Revenue_Combined_NPGs = []
for rev_df in _rev_dfs:
    if rev_df is None or rev_df.empty:
        All_Revenue_Combined_NPGs.append(pd.DataFrame())
        continue

    # normalize join keys to Int64 for stable merges
    for c in ["proj_network_id", "primary_ntwrk_id", "secondary_ntwrk_id"]:
        if c in rev_df.columns:
            rev_df[c] = pd.to_numeric(rev_df[c], errors="coerce").astype("Int64")

    out_df = rev_df.merge(proj_map, on="proj_network_id", how="left")
    out_df = out_df.merge(prim_map, on="primary_ntwrk_id", how="left")
    out_df = out_df.merge(sec_map,  on="secondary_ntwrk_id", how="left")

    All_Revenue_Combined_NPGs.append(out_df)

# Optional: one combined DF
final_df = pd.concat([d for d in All_Revenue_Combined_NPGs if d is not None and not d.empty], ignore_index=True)

print("Done.")
print("rows(final_df) =", 0 if final_df is None else len(final_df))
display(final_df)
