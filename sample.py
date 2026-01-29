# =========================
# Cell 11 (copy/paste)
# =========================
from pyspark.sql import functions as F
from pyspark.sql import DataFrame as SparkDF

# --- helpers ---
def _is_true(v):
    return str(v).strip().lower() in ("true", "1", "yes", "y")

def _is_empty_df(df):
    if df is None:
        return True
    if isinstance(df, SparkDF):
        # Spark-safe "is empty" (action)
        return df.rdd.isEmpty()
    # pandas fallback (if your connector ever returns pandas)
    return getattr(df, "empty", False) or (hasattr(df, "__len__") and len(df) == 0)

def _safe_and(filter_sql):
    """
    Your rev_base_dict has strings like pg['excl_retail'] / pg['excl_mail'].
    If they are empty/None -> no-op.
    If they already include leading AND, we won't double it.
    """
    if not filter_sql:
        return ""
    s = str(filter_sql).strip()
    if not s:
        return ""
    if s.lower().startswith("and "):
        return f"\n{s}"
    return f"\nAND {s}"

def _chunked(iterable, size=5000):
    buf = []
    for x in iterable:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf

def build_revenue_query(pg, channel_name, srx_arr_in, extra_filter_sql=""):
    """
    Revenue query ONLY hits: comp_engine_microservice_qa.revenue rs
    We do NOT join artifactsdb here. We'll join titles later.
    """
    uw_req_id = pg["uw_req_id"]
    proj_year = int(pg["proj_year"])
    npg = pg["network_pricing_group_id"]
    rpg = pg["rebate_pricing_group_id"]
    spg = pg["srx_pricing_group_id"]
    network_guid = pg["network_guid"]
    formulary_guid = pg["formulary_guid"]

    # These two are constants per pg; keeping them as literals prevents GROUP BY mistakes
    brand_generic_key = int(pg.get("brand_generic_key", 0) or 0)
    days_supply_key = int(_is_true(pg.get("days_supply_key", False)))

    # IMPORTANT: cast string ids to VARCHAR so Spark doesn't show them as binary
    # IMPORTANT: group by explicit column names (not positions)
    q = f"""
SELECT
  CAST(rs.uw_req_id AS VARCHAR(32))                      AS uw_req_id,
  CAST(rs.network_pricing_group_id AS VARCHAR(32))       AS network_pricing_group_id,
  CAST(rs.rebate_pricing_group_id AS VARCHAR(32))        AS rebate_pricing_group_id,
  CAST(rs.srx_pricing_group_id AS VARCHAR(32))           AS srx_pricing_group_id,

  CAST(rs.proj_year AS INT)                              AS proj_year,
  CAST(rs.proj_network_id AS BIGINT)                     AS proj_network_id,
  CAST(rs.primary_ntwrk_id AS BIGINT)                    AS primary_ntwrk_id,
  CAST(rs.secondary_ntwrk_id AS BIGINT)                  AS secondary_ntwrk_id,
  CAST(rs.tertiary_ntwrk_id AS BIGINT)                   AS tertiary_ntwrk_id,

  CAST(rs.network_guid AS VARCHAR(32))                   AS network_guid,
  CAST(rs.formulary_guid AS VARCHAR(32))                 AS formulary_guid,

  CASE WHEN {brand_generic_key} = 1 THEN 'Generic' ELSE 'Brand' END AS Brand_Generic,
  CAST(rs.mc AS TINYINT)                                 AS mc,
  CAST(rs.cstm_ntwk_ind AS INT)                          AS cstm_ntwk_ind,
  CAST(rs.cop_ind AS INT)                                AS cop_ind,

  '{channel_name}'                                       AS Channel,
  {days_supply_key}                                      AS days_supply,

  CAST(rs.cp_fin_sc_id AS VARCHAR(50))                   AS cp_fin_sc_id,
  CAST(rs.price_type_id AS INT)                          AS price_type_id,
  CAST(rs.network_pref_ind_id AS INT)                    AS network_pref_ind_id,
  CAST(rs.pharmacy_group_id AS INT)                      AS pharmacy_group_id,
  CAST(rs.pharmacy_capped_noncappped_id AS INT)          AS pharmacy_capped_noncappped_id,

  -- measures
  SUM(rs.num_claims)                      AS NumClaims,
  SUM(rs.awp_total)                       AS AWP_Total,
  SUM(rs.acquisition_cost)                AS Acquisition_Cost,

  SUM(rs.cogs_trad_pbm_total)             AS Cogs_Trad_PBM_Total,
  SUM(rs.cogs_trans_pbm_total)            AS Cogs_Trans_PBM_Total,
  SUM(rs.cogs_dispns_fee_trad_pbm_total)  AS Cogs_Dispns_Fee_Trad_PBM_Total,
  SUM(rs.cogs_dispns_fee_trans_pbm_total) AS Cogs_Dispns_Fee_Trans_PBM_Total,

  SUM(rs.cogs_trad_medi_total)            AS Cogs_Trad_Medi_Total,
  SUM(rs.cogs_trans_medi_total)           AS Cogs_Trans_Medi_Total,
  SUM(rs.cogs_dispns_fee_trad_medi_total) AS Cogs_Dispns_Fee_Trad_Medi_Total,
  SUM(rs.cogs_dispns_fee_trans_medi_total)AS Cogs_Dispns_Fee_Trans_Medi_Total,

  SUM(rs.mac_list_9)                      AS MAC_List_9,
  SUM(rs.mac_list_10)                     AS MAC_List_10

FROM comp_engine_microservice_qa.revenue rs
WHERE rs.uw_req_id = '{uw_req_id}'
  AND rs.srx_arrangement_key IN ({",".join(str(x) for x in srx_arr_in)})
  AND rs.proj_year = {proj_year}
  AND rs.network_pricing_group_id = '{npg}'
  AND rs.rebate_pricing_group_id  = '{rpg}'
  AND rs.srx_pricing_group_id     = '{spg}'
  AND rs.network_guid             = '{network_guid}'
  AND rs.formulary_guid           = '{formulary_guid}'
  {extra_filter_sql}

GROUP BY
  CAST(rs.uw_req_id AS VARCHAR(32)),
  CAST(rs.network_pricing_group_id AS VARCHAR(32)),
  CAST(rs.rebate_pricing_group_id AS VARCHAR(32)),
  CAST(rs.srx_pricing_group_id AS VARCHAR(32)),

  CAST(rs.proj_year AS INT),
  CAST(rs.proj_network_id AS BIGINT),
  CAST(rs.primary_ntwrk_id AS BIGINT),
  CAST(rs.secondary_ntwrk_id AS BIGINT),
  CAST(rs.tertiary_ntwrk_id AS BIGINT),

  CAST(rs.network_guid AS VARCHAR(32)),
  CAST(rs.formulary_guid AS VARCHAR(32)),

  CAST(rs.mc AS TINYINT),
  CAST(rs.cstm_ntwk_ind AS INT),
  CAST(rs.cop_ind AS INT),

  CAST(rs.cp_fin_sc_id AS VARCHAR(50)),
  CAST(rs.price_type_id AS INT),
  CAST(rs.network_pref_ind_id AS INT),
  CAST(rs.pharmacy_group_id AS INT),
  CAST(rs.pharmacy_capped_noncappped_id AS INT)

ORDER BY proj_year, network_pricing_group_id, Channel
"""
    return q

def fetch_network_titles(all_ids):
    """
    Pull titles from artifactsdb_qa.network for ids in all_ids (chunked).
    Returns a Spark DF with [id, title]
    """
    ids = sorted({int(x) for x in all_ids if x is not None})
    if not ids:
        return None

    dfs = []
    for chunk in _chunked(ids, size=5000):
        in_list = ",".join(str(i) for i in chunk)
        q = f"""
        SELECT CAST(id AS BIGINT) AS id, title
        FROM artifactsdb_qa.network
        WHERE id IN ({in_list})
        """
        d = starrocksConnection_qa("artifactsdb_qa", q)
        if not _is_empty_df(d):
            dfs.append(d)

    if not dfs:
        return None

    out = dfs[0]
    for d in dfs[1:]:
        out = out.unionByName(d, allowMissingColumns=True)
    return out.dropDuplicates(["id"])

def attach_network_titles(df, net_df):
    """
    Adds projected_network / primary_network / secondary_network by joining net_df 3 times.
    """
    if _is_empty_df(df) or _is_empty_df(net_df):
        return df

    # Ensure join key types match
    df = (df
          .withColumn("proj_network_id", F.col("proj_network_id").cast("long"))
          .withColumn("primary_ntwrk_id", F.col("primary_ntwrk_id").cast("long"))
          .withColumn("secondary_ntwrk_id", F.col("secondary_ntwrk_id").cast("long"))
          .withColumn("tertiary_ntwrk_id", F.col("tertiary_ntwrk_id").cast("long"))
    )

    n = F.broadcast(net_df.select(F.col("id").cast("long").alias("nid"), F.col("title").alias("ntitle")))

    df = (df
          .join(n.withColumnRenamed("nid", "proj_network_id").withColumnRenamed("ntitle", "projected_network"),
                on="proj_network_id", how="left")
          .join(n.withColumnRenamed("nid", "primary_ntwrk_id").withColumnRenamed("ntitle", "primary_network"),
                on="primary_ntwrk_id", how="left")
          .join(n.withColumnRenamed("nid", "secondary_ntwrk_id").withColumnRenamed("ntitle", "secondary_network"),
                on="secondary_ntwrk_id", how="left")
    )

    return df

# =========================
# MAIN LOGIC (rev_base_dict -> Revenue_Combined_NPGs)
# =========================
Revenue_Combined_NPGs = []
_all_network_ids = set()

for pg in rev_base_dict:
    # ---- retail query (srx_arrangement_key IN (1,3)) ----
    retail_q = build_revenue_query(
        pg=pg,
        channel_name="Retail",
        srx_arr_in=[1, 3],
        extra_filter_sql=_safe_and(pg.get("excl_retail"))
    )
    retail_df = starrocksConnection_qa("comp_engine_microservice_qa", retail_q)
    if not _is_empty_df(retail_df):
        Revenue_Combined_NPGs.append(retail_df)
        _all_network_ids.update([r["proj_network_id"] for r in retail_df.select("proj_network_id").distinct().collect() if r["proj_network_id"] is not None])
        _all_network_ids.update([r["primary_ntwrk_id"] for r in retail_df.select("primary_ntwrk_id").distinct().collect() if r["primary_ntwrk_id"] is not None])
        _all_network_ids.update([r["secondary_ntwrk_id"] for r in retail_df.select("secondary_ntwrk_id").distinct().collect() if r["secondary_ntwrk_id"] is not None])

    # ---- mail query (srx_arrangement_key IN (2)) ----
    mail_q = build_revenue_query(
        pg=pg,
        channel_name="Mail",
        srx_arr_in=[2],
        extra_filter_sql=_safe_and(pg.get("excl_mail"))
    )
    mail_df = starrocksConnection_qa("comp_engine_microservice_qa", mail_q)
    if not _is_empty_df(mail_df):
        Revenue_Combined_NPGs.append(mail_df)
        _all_network_ids.update([r["proj_network_id"] for r in mail_df.select("proj_network_id").distinct().collect() if r["proj_network_id"] is not None])
        _all_network_ids.update([r["primary_ntwrk_id"] for r in mail_df.select("primary_ntwrk_id").distinct().collect() if r["primary_ntwrk_id"] is not None])
        _all_network_ids.update([r["secondary_ntwrk_id"] for r in mail_df.select("secondary_ntwrk_id").distinct().collect() if r["secondary_ntwrk_id"] is not None])

    # ---- SRx at Retail query (srx_arrangement_key IN (4)) only when pg['srx_at_retail'] is false ----
    if not _is_true(pg.get("srx_at_retail")):
        srx_q = build_revenue_query(
            pg=pg,
            channel_name="SRx at Retail",
            srx_arr_in=[4],
            extra_filter_sql=""  # add pg.get("excl_srx_retail") if you have one
        )
        srx_df = starrocksConnection_qa("comp_engine_microservice_qa", srx_q)
        if not _is_empty_df(srx_df):
            Revenue_Combined_NPGs.append(srx_df)
            _all_network_ids.update([r["proj_network_id"] for r in srx_df.select("proj_network_id").distinct().collect() if r["proj_network_id"] is not None])
            _all_network_ids.update([r["primary_ntwrk_id"] for r in srx_df.select("primary_ntwrk_id").distinct().collect() if r["primary_ntwrk_id"] is not None])
            _all_network_ids.update([r["secondary_ntwrk_id"] for r in srx_df.select("secondary_ntwrk_id").distinct().collect() if r["secondary_ntwrk_id"] is not None])

# ---- fetch titles once, then attach to each DF ----
net_df = fetch_network_titles(_all_network_ids)

Revenue_Combined_NPGs = [attach_network_titles(d, net_df) for d in Revenue_Combined_NPGs]

# If you want one combined DF:
# from functools import reduce
# final_df = reduce(lambda a,b: a.unionByName(b, allowMissingColumns=True), Revenue_Combined_NPGs) if Revenue_Combined_NPGs else None
# display(final_df)

