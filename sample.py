import pandas as pd

All_Revenue_Combined_NPGs = []

_rev_dfs = []
_all_network_ids = set()

for pg in rev_base_dict:

    # ---- keep your year mapping ----
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

    # ---- Revenue query ONLY (force types to avoid CANNOT_DETERMINE_TYPE) ----
    revenue_q = f"""
    SELECT
        CAST(rs.uw_req_id AS VARCHAR) AS uw_req_id,
        CAST(rs.network_pricing_group_id AS VARCHAR) AS network_pricing_group_id,
        CAST(rs.rebate_pricing_group_id  AS VARCHAR) AS rebate_pricing_group_id,
        CAST(rs.srx_pricing_group_id     AS VARCHAR) AS srx_pricing_group_id,
        CAST(rs.proj_year AS INT) AS proj_year,

        CAST(rs.proj_network_id    AS BIGINT) AS proj_network_id,
        CAST(rs.primary_ntwrk_id   AS BIGINT) AS primary_ntwrk_id,
        CAST(rs.secondary_ntwrk_id AS BIGINT) AS secondary_ntwrk_id,
        CAST(rs.tertiary_ntwrk_id  AS BIGINT) AS tertiary_ntwrk_id,

        CAST(COALESCE(rs.network_guid, '')   AS VARCHAR) AS network_guid,
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

        -- tag_* columns are the usual culprit: force INT with COALESCE
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

        -- aggregates (cast to DOUBLE for stable typing)
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

    -- IMPORTANT: group only by NON-aggregate columns (first 35 select items)
    GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,
             21,22,23,24,25,26,27,28,29,30,31,32,33,34,35
    ORDER BY 5,12,16
    """

    rev_df = starrocksConnection_qa("comp_engine_microservice_qa", revenue_q)

    if rev_df is None or len(rev_df) == 0:
        _rev_dfs.append(pd.DataFrame())
        continue

    # Normalize ids for the artifacts lookup and merges
    for col in ["proj_network_id", "primary_ntwrk_id", "secondary_ntwrk_id"]:
        if col in rev_df.columns:
            rev_df[col] = pd.to_numeric(rev_df[col], errors="coerce").astype("Int64")
            _all_network_ids.update(rev_df[col].dropna().astype(int).tolist())

    _rev_dfs.append(rev_df)


# ---- Query artifactsdb once, then merge titles in Pandas ----
if _all_network_ids:
    in_list = ",".join(str(x) for x in sorted(_all_network_ids))
    net_q = f"SELECT CAST(id AS BIGINT) AS id, CAST(title AS VARCHAR) AS title FROM artifactsdb_qa.network WHERE id IN ({in_list})"
    net_df = starrocksConnection_qa("artifactsdb_qa", net_q)
else:
    net_df = pd.DataFrame(columns=["id", "title"])

if net_df is None or len(net_df) == 0:
    net_df = pd.DataFrame(columns=["id", "title"])
else:
    net_df["id"] = pd.to_numeric(net_df["id"], errors="coerce").astype("Int64")

proj_map = net_df.rename(columns={"id": "proj_network_id", "title": "projected_network"})
prim_map = net_df.rename(columns={"id": "primary_ntwrk_id", "title": "primary_network"})
sec_map  = net_df.rename(columns={"id": "secondary_ntwrk_id", "title": "secondary_network"})

for rev_df in _rev_dfs:
    if rev_df is None or len(rev_df) == 0:
        All_Revenue_Combined_NPGs.append(rev_df)
        continue

    out_df = rev_df.merge(proj_map, on="proj_network_id", how="left")
    out_df = out_df.merge(prim_map, on="primary_ntwrk_id", how="left")
    out_df = out_df.merge(sec_map,  on="secondary_ntwrk_id", how="left")

    All_Revenue_Combined_NPGs.append(out_df)
