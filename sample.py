SELECT
  $__timeGroup(updated_at, '1m') AS time,
  AVG(TIMESTAMPDIFF(SECOND, started_at, updated_at)) AS value,
  'StarRocks' AS metric
FROM comp_engine_microservice_qa.model_parameters
WHERE
  status = 'Completed'
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo()
  AND started_at IS NOT NULL
  AND updated_at IS NOT NULL
GROUP BY 1
ORDER BY 1;



/////////////


SELECT
  $__timeGroup(updated_at, '1m') AS time,
  AVG(TIMESTAMPDIFF(SECOND, started_at, updated_at)) AS value,
  'MySQL' AS metric
FROM comp_engine_microservice.model_parameters
WHERE
  status = 'Completed'
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo()
  AND started_at IS NOT NULL
  AND updated_at IS NOT NULL
GROUP BY 1
ORDER BY 1;



//////////////////

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
  AND started_at IS NOT NULL
  AND updated_at IS NOT NULL
ORDER BY updated_at DESC
LIMIT 200;



//////////////


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
  AND started_at IS NOT NULL
  AND updated_at IS NOT NULL
ORDER BY updated_at DESC
LIMIT 200;


