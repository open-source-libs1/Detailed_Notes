SELECT
  uw_req_id, proj_year,
  network_pricing_group_id, rebate_pricing_group_id, srx_pricing_group_id,
  network_guid, formulary_guid,
  srx_arrangement_key, days_supply_key, brand_generic_key
FROM comp_engine_microservice_output_qa.pricing_group_claims_agg
WHERE uw_req_id = '<PUT_UW_REQ_ID>'
LIMIT 20;


/////


DESCRIBE comp_engine_microservice_qa.revenue;



//////////


SELECT COUNT(*) AS cnt
FROM comp_engine_microservice_qa.revenue rs
WHERE rs.uw_req_id = '<PUT_UW_REQ_ID>'
  AND rs.proj_year = <PUT_YEAR>
  AND rs.network_pricing_group_id = '<PUT_NPG_ID>'
  AND rs.rebate_pricing_group_id  = '<PUT_RPG_ID>'
  AND rs.srx_pricing_group_id     = '<PUT_SPG_ID>'
  AND rs.network_guid             = '<PUT_NETWORK_GUID>'
  AND rs.formulary_guid           = '<PUT_FORMULARY_GUID>';
