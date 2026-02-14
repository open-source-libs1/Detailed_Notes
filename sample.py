SELECT
  uw_req_id,
  scenario_id,
  started_at,
  updated_at,
  TIMESTAMPDIFF(SECOND, started_at, updated_at) AS duration_seconds
FROM comp_engine_microservice_qa.model_parameters
WHERE
  status = 'Completed'
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo()
ORDER BY updated_at DESC
LIMIT 200;



/////////////


SELECT
  BIN_TO_UUID(uw_req_id) AS uw_req_id,
  BIN_TO_UUID(scenario_id) AS scenario_id,
  started_at,
  updated_at,
  TIMESTAMPDIFF(SECOND, started_at, updated_at) AS duration_seconds
FROM comp_engine_microservice.model_parameters
WHERE
  status = 'Completed'
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo()
ORDER BY updated_at DESC
LIMIT 200;
