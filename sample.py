filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
let wf_error = extract_regex(cloudwatch_log, 'message\\\\":\\\\"([^\\\\"]+)')
statsby count() by wf_error
sort count desc
