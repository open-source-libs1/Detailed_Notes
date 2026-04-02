filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
filter cloudwatch_log ~ "Got Validation Errors"
extract_regex cloudwatch_log, /"message":\s*"Got Validation Errors (?P<validation_error>[^"]+)"/
statsby err_count: count(1), group_by(validation_error)
sort err_count
