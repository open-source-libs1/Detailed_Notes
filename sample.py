filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
extract_regex cloudwatch_log, /message\\\\":\\\\"(?P<wf_error>[^\\\\"]+)/
statsby count: count() by wf_error
sort -count


--------------



filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "RequestException for Workfront request after retry"
extract_regex cloudwatch_log, /Error: \{\\?"error\\?":\{\\?"message\\?":\\?"(?P<wf_error>[^\\"]+)/
statsby count: count() by wf_error
sort -count
