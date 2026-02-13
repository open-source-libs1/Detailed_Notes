SELECT
  COUNT(*) AS value
FROM comp_engine_microservice_qa.model_parameters
WHERE
  status = 'Completed'
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo();



////////////////


SELECT
  COUNT(*) AS value
FROM comp_engine_microservice_qa.model_parameters
WHERE
  status = 'Failed'
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo();



////////////////

SELECT
  COUNT(*) AS value
FROM comp_engine_microservice_qa.model_parameters
WHERE
  status = 'In Progress'
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo();



////////////////////


SELECT
  status,
  COUNT(*) AS cnt
FROM comp_engine_microservice_qa.model_parameters
WHERE
  updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo()
GROUP BY status
ORDER BY cnt DESC;



/////////////////////


SELECT
  $__timeGroup(updated_at, '5m') AS time,
  AVG(TIMESTAMPDIFF(SECOND, started_at, updated_at)) / 60.0 AS avg_minutes
FROM comp_engine_microservice_qa.model_parameters
WHERE
  status = 'Completed'
  AND started_at IS NOT NULL
  AND updated_at IS NOT NULL
  AND updated_at >= $__timeFrom()
  AND updated_at <= $__timeTo()
GROUP BY 1
ORDER BY 1;



//////////////////////


