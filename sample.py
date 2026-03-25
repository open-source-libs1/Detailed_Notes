filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
extract_regex cloudwatch_log, /message\\\\":\\\\"(?P<wf_error>[^\\\\"]+)/
statsby err_count: count(1), group_by(wf_error)
sort err_count desc
