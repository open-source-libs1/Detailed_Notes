filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "offer-details-synchronization-consumer"
statsby log_count: count(1), group_by(region)
sort -log_count
limit 1
