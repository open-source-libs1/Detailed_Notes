filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
parse regex field=cloudwatch_log 'Error: .*?message\\\\":\\\\"(?<wf_error>[^\\\\"]+)'
statsby count() by wf_error
