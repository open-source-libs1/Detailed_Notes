from pyspark.sql import functions as F

def _boolish(v):
    # handles True/False, "true"/"false", 1/0, "1"/"0"
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("true", "1", "yes", "y")

def _sql_quote(v):
    # safe for GUID-like strings
    if v is None:
        return ""
    return str(v).replace("'", "''")

def _safe_and(extra_sql):
    # allow pg['excl_*'] to be None/"None"/""; otherwise prefix with AND if not already
    if extra_sql is None:
        return ""
    s = str(extra_sql).strip()
    if s == "" or s.lower() == "none":
        return ""
    return s if s.lower().lstrip().startswith("and ") else f"AND {s}"

def _is_empty_df(df):
    # Spark-safe emptiness check
    return (df is None) or df.rdd.isEmpty()

def build_revenue_query(pg, srx_arr_in, channel_label, extra_filter_sql=None):
    # IMPORTANT: these are column names in rs; your dict seems to store the names
    brand_col = pg.get("brand_generic_key", "brand_generic_key")
    srx_col   = pg.get("srx_arrangement_key", "srx_arrangement_key")
    days_col  = pg.get("days_supply_key", "days_supply_key")

    # year is numeric in DB; keep it numeric
    year_val = int(pg.get("proj_year", 0))

    uw_req_id = _sql_quote(pg.get("uw_req_id"))
    npg_id    = _sql_quote(pg.get("network_pricing_group_id"))
    rpg_id    = _sql_quote(pg.get("rebate_pricing_group_id"))
    srxpg_id  = _sql_quote(pg.get("srx_pricing_group_id"))
    net_guid  = _sql_quote(pg.get("network_guid"))
    form_guid = _sql_quote(pg.get("formulary_guid"))

    srx_list_sql = ",".join(str(int(x)) for x in srx_arr_in)

    q = f"""
    SELECT
        rs.uw_req_id,
        rs.network_pricing_group_id,
        rs.rebate_pricing_group_id,
        rs.srx_pricing_group_id,
        rs.proj_year,
        rs.proj_network_id,  n.title  AS projected_network,
        rs.primary_ntwrk_id, pn.title AS primary_network,
        rs.secondary_ntwrk_id, sn.title AS secondary_network,
        rs.tertiary_ntwrk_id,
        rs.network_guid,
        rs.formulary_guid,

        CASE rs.{brand_col}
            WHEN 1 THEN 'Generic'
            ELSE 'Brand'
        END AS Brand_Generic,

        rs.mc,
        rs.cstm_ntwk_ind,
        rs.cop_ind,

        CASE rs.{srx_col}
            WHEN 1 THEN 'Retail'
            WHEN 2 THEN 'Mail'
            WHEN 3 THEN 'Specialty'
            WHEN 4 THEN 'SRx at Retail'
            ELSE 'NA'
        END AS Channel,

        CASE rs.{days_col}
            WHEN 1 THEN 1
            ELSE 0
        END AS days_supply,

        rs.cp_fin_sc_id,
        rs.price_type_id,
        rs.network_pref_ind_id,
        rs.pharmacy_group_id,
        rs.pharmacy_capped_noncapped_id,

        SUM(rs.num_claims)           AS NumClaims,
        SUM(rs.awp_total)            AS AWP_Total,
        SUM(rs.acquisition_cost)     AS Acquisition_Cost,
        SUM(rs.cogs_trad_pbm_total)  AS Cogs_Trad_PBM_Total,
        SUM(rs.cogs_trans_pbm_total) AS Cogs_Trans_PBM_Total,
        SUM(rs.cogs_dispns_fee_trad_pbm_total)  AS Cogs_Dispns_Fee_Trad_PBM_Total,
        SUM(rs.cogs_dispns_fee_trans_pbm_total) AS Cogs_Dispns_Fee_Trans_PBM_Total,
        SUM(rs.cogs_trad_medi_total)            AS Cogs_Trad_Medi_Total,
        SUM(rs.cogs_trans_medi_total)           AS Cogs_Trans_Medi_Total,
        SUM(rs.cogs_dispns_fee_trad_medi_total) AS Cogs_Dispns_Fee_Trad_Medi_Total,
        SUM(rs.cogs_dispns_fee_trans_medi_total)AS Cogs_Dispns_Fee_Trans_Medi_Total,
        SUM(rs.mac_list_9)           AS MAC_List_9,
        SUM(rs.mac_list_10)          AS MAC_List_10

    FROM comp_engine_microservice_qa.revenue rs
    LEFT JOIN artifactsdb_qa.network n  ON rs.proj_network_id     = n.id
    LEFT JOIN artifactsdb_qa.network sn ON rs.secondary_ntwrk_id  = sn.id
    LEFT JOIN artifactsdb_qa.network pn ON rs.primary_ntwrk_id    = pn.id

    WHERE rs.uw_req_id = '{uw_req_id}'
      AND rs.{srx_col} IN ({srx_list_sql})
      AND rs.proj_year = {year_val}
      AND rs.network_pricing_group_id = '{npg_id}'
      AND rs.rebate_pricing_group_id  = '{rpg_id}'
      AND rs.srx_pricing_group_id     = '{srxpg_id}'
      AND rs.network_guid   = '{net_guid}'
      AND rs.formulary_guid = '{form_guid}'
      {_safe_and(extra_filter_sql)}

    GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25
    ORDER BY 5,12,16
    """
    return q

def run_rev_query(label, query):
    # optional: print(label, query) if you want to debug SQL text
    df = starrocksConnection_qa("comp_engine_microservice_qa", query)

    # normalize a couple of types that often come back weird in JDBC
    if df is not None and "uw_req_id" in df.columns:
        df = df.withColumn("uw_req_id", F.col("uw_req_id").cast("string"))
    return df

Revenue_Combined_NPGs = []

for pg in rev_base_dict:
    # 1) Retail (1,3)
    retail_q = build_revenue_query(
        pg=pg,
        srx_arr_in=[1, 3],
        channel_label="Retail",
        extra_filter_sql=pg.get("excl_retail")
    )
    retail_df = run_rev_query("retail", retail_q)
    if not _is_empty_df(retail_df):
        Revenue_Combined_NPGs.append(retail_df)

    # 2) SRx_at_Retail (4) — run only when your dict says so
    # Your screenshots show: if pg["srx_at_retail"] == 'false' then run SRx retail
    if str(pg.get("srx_at_retail", "")).strip().lower() == "false":
        srx_retail_q = build_revenue_query(
            pg=pg,
            srx_arr_in=[4],
            channel_label="SRx at Retail",
            extra_filter_sql=pg.get("excl_retail")  # adjust if you have a separate excl_srx_retail
        )
        srx_retail_df = run_rev_query("srx_retail", srx_retail_q)
        if not _is_empty_df(srx_retail_df):
            Revenue_Combined_NPGs.append(srx_retail_df)

    # 3) Mail (2)
    mail_q = build_revenue_query(
        pg=pg,
        srx_arr_in=[2],
        channel_label="Mail",
        extra_filter_sql=pg.get("excl_mail")
    )
    mail_df = run_rev_query("mail", mail_q)
    if not _is_empty_df(mail_df):
        Revenue_Combined_NPGs.append(mail_df)

# OPTIONAL: one combined DF
# from functools import reduce
# final_df = reduce(lambda a, b: a.unionByName(b, allowMissingColumns=True), Revenue_Combined_NPGs)
# display(final_df)

Revenue_Combined_NPGs
