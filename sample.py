import pandas as pd

All_Revenue_Combined_NPGs = []

# We'll first collect all revenue dfs + all network ids, then do ONE artifactsdb lookup (faster + cleaner)
_rev_dfs = []
_all_network_ids = set()

for pg in rev_base_dict:

    # ---- keep your year-mapping logic (but store as INT for SQL) ----
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

    # ---- Revenue query ONLY (no artifactsdb_qa references) ----
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

        CASE rs.{pg["brand_generic_key"]}
            WHEN 1 THEN 'Generic'
            ELSE 'Brand'
        END AS Brand_Generic,

        rs.mc,
        rs.cstm_ntwk_ind,
        rs.cop_ind,

        CASE rs.{pg["srx_arrangement_key"]}
            WHEN 1 THEN 'Retail'
            WHEN 2 THEN 'Mail'
            WHEN 3 THEN 'Specialty'
            WHEN 4 THEN 'SRx at Retail'
            ELSE 'NA'
        END AS Channel,

        CASE
            WHEN rs.{pg["days_supply_key"]} = 1 OR rs.{pg["days_supply_key"]} = TRUE THEN 1
            ELSE 0
        END AS days_supply,

        rs.cp_fin_sc_id,
        rs.price_type_id,
        rs.network_pref_ind_id,
        rs.pharmacy_capped_noncapped_id,
        rs.tag_paper_claims,
        rs.tag_340b,
        rs.tag_340b_clm,
        rs.tag_340b_pharm,
        rs.tag_340b_phmcy38,
        rs.tag_340b_phmcy39,
        rs.tag_340b_std_phmcy37,
        rs.tag_340b_mfg_phmcy_discnt,
        rs.tag_340b_phmcy38_scc20,
        rs.tag_340b_phmcy39_scc20,
        rs.tag_340b_ineligible,
        rs.tag_340b_phmcy_w_scc20,
        rs.tag_340b_phmcy38_phmcy39_w_scc20,
        rs.tag_coordination_of_benefits,

        SUM(rs.num_claims) AS NumClaims,
        SUM(rs.awp_total) AS AWP_Total,
        SUM(rs.acquisition_cost) AS Acquisition_Cost,
        SUM(rs.cogs_trad_pbm_total) AS Cogs_Trad_PBM_Total,
        SUM(rs.cogs_trans_pbm_total) AS Cogs_Trans_PBM_Total,
        SUM(rs.cogs_dispns_fee_trad_pbm_total) AS Cogs_Dispns_Fee_Trad_PBM_Total,
        SUM(rs.cogs_dispns_fee_trans_pbm_total) AS Cogs_Dispns_Fee_Trans_PBM_Total,
        SUM(rs.cogs_trad_medi_total) AS Cogs_Trad_Medi_Total,
        SUM(rs.cogs_trans_medi_total) AS Cogs_Trans_Medi_Total,
        SUM(rs.cogs_dispns_fee_trad_medi_total) AS Cogs_Dispns_Fee_Trad_Medi_Total,
        SUM(rs.cogs_dispns_fee_trans_medi_total) AS Cogs_Dispns_Fee_Trans_Medi_Total,
        SUM(rs.mac_list_9) AS MAC_List_9,
        SUM(rs.mac_list_10) AS MAC_List_10

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
             21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37
    ORDER BY 5,12,16
    """

    rev_df = starrocksConnection_qa("comp_engine_microservice_qa", revenue_q)

    # Always keep list alignment
    if rev_df is None or len(rev_df) == 0:
        _rev_dfs.append(pd.DataFrame())
        continue

    # Normalize ID columns so the Pandas join is stable
    for col in ["proj_network_id", "primary_ntwrk_id", "secondary_ntwrk_id"]:
        if col in rev_df.columns:
            rev_df[col] = pd.to_numeric(rev_df[col], errors="coerce").astype("Int64")

    # Collect ids needed for artifacts lookup
    for col in ["proj_network_id", "primary_ntwrk_id", "secondary_ntwrk_id"]:
        if col in rev_df.columns:
            vals = rev_df[col].dropna().astype(int).tolist()
            _all_network_ids.update(vals)

    _rev_dfs.append(rev_df)


# ---- Now lookup all network titles ONCE from artifactsdb_qa ----
if _all_network_ids:
    in_list = ",".join(str(x) for x in sorted(_all_network_ids))
    net_q = f"""
    SELECT id, title
    FROM artifactsdb_qa.network
    WHERE id IN ({in_list})
    """
    net_df = starrocksConnection_qa("artifactsdb_qa", net_q)
else:
    net_df = pd.DataFrame(columns=["id", "title"])

# Normalize net_df ids
if net_df is None or len(net_df) == 0:
    net_df = pd.DataFrame(columns=["id", "title"])
else:
    net_df["id"] = pd.to_numeric(net_df["id"], errors="coerce").astype("Int64")

# ---- Enrich each revenue df with titles ----
proj_map = net_df.rename(columns={"id": "proj_network_id", "title": "projected_network"})
prim_map = net_df.rename(columns={"id": "primary_ntwrk_id", "title": "primary_network"})
sec_map  = net_df.rename(columns={"id": "secondary_ntwrk_id", "title": "secondary_network"})

for rev_df in _rev_dfs:
    if rev_df is None or len(rev_df) == 0:
        # Keep consistent output shape (optional)
        All_Revenue_Combined_NPGs.append(rev_df)
        continue

    out_df = rev_df.merge(proj_map, on="proj_network_id", how="left")
    out_df = out_df.merge(prim_map, on="primary_ntwrk_id", how="left")
    out_df = out_df.merge(sec_map,  on="secondary_ntwrk_id", how="left")

    All_Revenue_Combined_NPGs.append(out_df)
