filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
extract_regex arn, /arn:aws:logs:(?P<active_region>us-(?:east|west)-\d):/
statsby log_count: count(1), group_by(active_region)
sort -log_count
limit 1
