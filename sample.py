SELECT t.*
FROM comp_engine_microservice_output_qa.pnl_rebate_gpi_tc t
JOIN (
    SELECT
        gpi,
        proj_year
    FROM comp_engine_microservice_output_qa.pnl_rebate_gpi_tc
    WHERE scenario_id = '0806654E4DF2423184E818D213C09241'
      AND brand_generic = 1
    GROUP BY gpi, proj_year
    HAVING COUNT(*) > 1
) dup
ON t.gpi = dup.gpi
AND t.proj_year = dup.proj_year
WHERE t.scenario_id = '0806654E4DF2423184E818D213C09241'
  AND t.brand_generic = 1
ORDER BY t.proj_year, t.gpi;
