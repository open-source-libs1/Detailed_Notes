from pyspark.sql import functions as F

All_Revenue_Combined_NPGs = []
_rev_dfs = []
_all_ids = set()

def is_empty_df(df):
    # Works for Spark DataFrame
    return df is None or df.rdd.isEmpty()

def collect_ids_from_rev_df(df):
    # Collect only the 3 id columns to driver (usually small)
    id_cols = ["proj_network_id", "primary_ntwrk_id", "secondary_ntwrk_id"]
    present = [c for c in id_cols if c in df.columns]
    if not present:
        return set()

    ids_df = None
    for c in present:
        tmp = df.select(F.col(c).cast("long").alias("id")).where(F.col(c).isNotNull())
        ids_df = tmp if ids_df is None else ids_df.union(tmp)

    ids = [r["id"] for r in ids_df.distinct().collect()]
    return set(int(x) for x in ids if x is not None)

for pg in rev_base_dict:

    # ---- your year mapping ----
    if pg["proj_year"] == 0:
        year = 0
    elif pg["proj_year"] == 1:
        year = 1
    elif pg["proj_year"] == 2:
        year = 2
    elif pg["proj_year"] == 3:
        year = 3
    else:
        year = int(pg["proj_year"])

    # ---- Revenue query ONLY (no artifacts db references) ----
    # NOTE: group by only NON-aggregate columns (first 35 items before SUMs)
    revenue_q = f"""
    SELECT
        CAST(rs.uw_req_id AS VARCHAR) AS uw_req_id,
        CAST(rs.network_pricing_group_id AS VARCHAR) AS network_pricing_group_id,
        CAST(rs.rebate_pricing_group_id AS VARCHAR) AS rebate_pricing_group_id,
        CAST(rs.srx_pricing_group_id AS VARCHAR) AS srx_pricing_group_id,
        CAST(rs.proj_year AS INT) AS proj_year,

        CAST(rs.proj_network_id AS BIGINT) AS proj_network_id,
        CAST(rs.primary_ntwrk_id AS BIGINT) AS primary_ntwrk_id,
        CAST(rs.secondary_ntwrk_id AS BIGINT) AS secondary_ntwrk_id,
        CAST(rs.tertiary_ntwrk_id AS BIGINT) AS tertiary_ntwrk_id,

        CAST(COALESCE(rs.network_guid, '') AS VARCHAR) AS network_guid,
        CAST(COALESCE(rs.formulary_guid, '') AS VARCHAR) AS formulary_guid,

        CASE CAST(rs.{pg["brand_generic_key"]} AS INT)
            WHEN 1 THEN 'Generic'
            ELSE 'Brand'
        END AS Brand_Generic,

        CAST(COALESCE(rs.mc, 0) AS DOUBLE) AS mc,
        CAST(COALESCE(rs.cstm_ntwk_ind, 0) AS INT) AS cstm_ntwk_ind,
        CAST(COALESCE(rs.cop_ind, 0) AS INT) AS cop_ind,

        CASE CAST(rs.{pg["srx_arrangement_key"]} AS INT)
            WHEN 1 THEN 'Retail'
            WHEN 2 THEN 'Mail'
            WHEN 3 THEN 'Specialty'
            WHEN 4 THEN 'SRx at Retail'
            ELSE 'NA'
        END AS Channel,

        CASE
            WHEN CAST(COALESCE(rs.{pg["days_supply_key"]}, 0) AS INT) = 1 THEN 1
            ELSE 0
        END AS days_supply,

        CAST(COALESCE(rs.cp_fin_sc_id, 0) AS BIGINT) AS cp_fin_sc_id,
        CAST(COALESCE(rs.price_type_id, 0) AS BIGINT) AS price_type_id,
        CAST(COALESCE(rs.network_pref_ind_id, 0) AS BIGINT) AS network_pref_ind_id,
        CAST(COALESCE(rs.pharmacy_capped_noncapped_id, 0) AS BIGINT) AS pharmacy_capped_noncapped_id,

        CAST(COALESCE(rs.tag_paper_claims, 0) AS INT) AS tag_paper_claims,
        CAST(COALESCE(rs.tag_340b, 0) AS INT) AS tag_340b,
        CAST(COALESCE(rs.tag_340b_clm, 0) AS INT) AS tag_340b_clm,
        CAST(COALESCE(rs.tag_340b_pharm, 0) AS INT) AS tag_340b_pharm,
        CAST(COALESCE(rs.tag_340b_phmcy38, 0) AS INT) AS tag_340b_phmcy38,
        CAST(COALESCE(rs.tag_340b_phmcy39, 0) AS INT) AS tag_340b_phmcy39,
        CAST(COALESCE(rs.tag_340b_std_phmcy37, 0) AS INT) AS tag_340b_std_phmcy37,
        CAST(COALESCE(rs.tag_340b_mfg_phmcy_discnt, 0) AS INT) AS tag_340b_mfg_phmcy_discnt,
        CAST(COALESCE(rs.tag_340b_phmcy38_scc20, 0) AS INT) AS tag_340b_phmcy38_scc20,
        CAST(COALESCE(rs.tag_340b_phmcy39_scc20, 0) AS INT) AS tag_340b_phmcy39_scc20,
        CAST(COALESCE(rs.tag_340b_ineligible, 0) AS INT) AS tag_340b_ineligible,
        CAST(COALESCE(rs.tag_340b_phmcy_w_scc20, 0) AS INT) AS tag_340b_phmcy_w_scc20,
        CAST(COALESCE(rs.tag_340b_phmcy38_phmcy39_w_scc20, 0) AS INT) AS tag_340b_phmcy38_phmcy39_w_scc20,
        CAST(COALESCE(rs.tag_coordination_of_benefits, 0) AS INT) AS tag_coordination_of_benefits,

        CAST(SUM(rs.num_claims) AS DOUBLE) AS NumClaims,
        CAST(SUM(rs.awp_total) AS DOUBLE) AS AWP_Total,
        CAST(SUM(rs.acquisition_cost) AS DOUBLE) AS Acquisition_Cost,
        CAST(SUM(rs.cogs_trad_pbm_total) AS DOUBLE) AS Cogs_Trad_PBM_Total,
        CAST(SUM(rs.cogs_trans_pbm_total) AS DOUBLE) AS Cogs_Trans_PBM_Total,
        CAST(SUM(rs.cogs_dispns_fee_trad_pbm_total) AS DOUBLE) AS Cogs_Dispns_Fee_Trad_PBM_Total,
        CAST(SUM(rs.cogs_dispns_fee_trans_pbm_total) AS DOUBLE) AS Cogs_Dispns_Fee_Trans_PBM_Total,
        CAST(SUM(rs.cogs_trad_medi_total) AS DOUBLE) AS Cogs_Trad_Medi_Total,
        CAST(SUM(rs.cogs_trans_medi_total) AS DOUBLE) AS Cogs_Trans_Medi_Total,
        CAST(SUM(rs.cogs_dispns_fee_trad_medi_total) AS DOUBLE) AS Cogs_Dispns_Fee_Trad_Medi_Total,
        CAST(SUM(rs.cogs_dispns_fee_trans_medi_total) AS DOUBLE) AS Cogs_Dispns_Fee_Trans_Medi_Total,
        CAST(SUM(rs.mac_list_9) AS DOUBLE) AS MAC_List_9,
        CAST(SUM(rs.mac_list_10) AS DOUBLE) AS MAC_List_10

    FROM comp_engine_microservice_qa.revenue rs
    WHERE rs.uw_req_id = '{pg["uw_req_id"]}'
      AND rs.{pg["srx_arrangement_key"]} IN (1,2,3,4)
      AND rs.proj_year = {year}
      AND rs.network_pricing_group_id = '{pg["network_pricing_group_id"]}'
      AND rs.rebate_pricing_group_id  = '{pg["rebate_pricing_group_id"]}'
      AND rs.srx_pricing_group_id     = '{pg["srx_pricing_group_id"]}'
      AND rs.network_guid             = '{pg["network_guid"]}'
      AND rs.formulary_guid           = '{pg["formulary_guid"]}'

    GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,
             21,22,23,24,25,26,27,28,29,30,31,32,33,34,35
    ORDER BY 5,12,16
    """

    rev_df = starrocksConnection_qa("comp_engine_microservice_qa", revenue_q)

    if is_empty_df(rev_df):
        _rev_dfs.append(None)
        continue

    # Collect ids needed for artifacts query
    _all_ids |= collect_ids_from_rev_df(rev_df)
    _rev_dfs.append(rev_df)


# ---- Query artifactsdb once using IN list ----
if _all_ids:
    in_list = ",".join(str(x) for x in sorted(_all_ids))
    net_q = f"""
    SELECT CAST(id AS BIGINT) AS id, CAST(title AS VARCHAR) AS title
    FROM artifactsdb_qa.network
    WHERE id IN ({in_list})
    """
    net_df = starrocksConnection_qa("artifactsdb_qa", net_q)
else:
    net_df = None

# ---- Join titles back (Spark joins) ----
for rev_df in _rev_dfs:
    if rev_df is None:
        All_Revenue_Combined_NPGs.append(rev_df)
        continue

    if net_df is None or is_empty_df(net_df):
        # no titles available
        out_df = (rev_df
                  .withColumn("projected_network", F.lit(None).cast("string"))
                  .withColumn("primary_network",   F.lit(None).cast("string"))
                  .withColumn("secondary_network", F.lit(None).cast("string")))
        All_Revenue_Combined_NPGs.append(out_df)
        continue

    n1 = net_df.select(F.col("id").alias("proj_network_id"), F.col("title").alias("projected_network"))
    n2 = net_df.select(F.col("id").alias("primary_ntwrk_id"), F.col("title").alias("primary_network"))
    n3 = net_df.select(F.col("id").alias("secondary_ntwrk_id"), F.col("title").alias("secondary_network"))

    out_df = (rev_df
              .join(n1, on="proj_network_id", how="left")
              .join(n2, on="primary_ntwrk_id", how="left")
              .join(n3, on="secondary_ntwrk_id", how="left"))

    All_Revenue_Combined_NPGs.append(out_df)
