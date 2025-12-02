select distinct
  upper(replace(bin_to_uuid(scenario_id),'-','')) as scenario_id,
  lob_id,
  upper(replace(bin_to_uuid(uw_req_id),'-','')) as uw_req_id
from comp_engine_microservice.model_parameters mp
where updated_at >= now() - interval 4 hour
  and updated_at <  now() - interval 2 hour
  and status = 'Completed';

