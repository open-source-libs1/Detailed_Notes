filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "updated account to updateItemParam:"

parse_regex cloudwatch_log /\\\"promo_code\\\":\\\"(?<promo_code>[^\\\"]+)\\\"/
parse_regex cloudwatch_log /\\\"reward_amount\\\":\\\"(?<reward_amount>[0-9]+)\\\"/

make_col reward_amount_num = int64(reward_amount)

statsby sum(reward_amount_num), promo_code, timechart(timestamp, 1h)


/////////////////////


filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "updated account to updateItemParam:"

parse_regex cloudwatch_log /\\\"promo_code\\\":\\\"(?<promo_code>[^\\\"]+)\\\"/
parse_regex cloudwatch_log /\\\"reward_amount\\\":\\\"(?<reward_amount>[0-9]+)\\\"/

make_col reward_amount_num = int64(reward_amount)

statsby sum(reward_amount_num), promo_code, timestamp:1h                                                      
