filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
make_col wf_error: extract_regex(cloudwatch_log, 'message\\\\":\\\\"([^\\\\"]+)')
statsby count: count(), group_by(wf_error)
sort -count



-----------------


filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
make_col wf_error: extract_regex(cloudwatch_log, 'message\\\\":\\\\"([^\\\\"]+)')
statsby count: count() by wf_error


------------------


filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
make_col wf_error: regexp_extract(cloudwatch_log, 'message\\\\":\\\\"([^\\\\"]+)', 1)
statsby count: count() by wf_error
sort -count
