filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "{\"level\":\"info\",\"message\":\"updated account to updateItemParam:"

extract_regex cloudwatch_log, /promo_code\\":\\"(?P<promocode>[^\\"]+)/
extract_regex cloudwatch_log, /reward_amount\\":\\"(?P<rewardamount::int64>[0-9]+)/

timechart 1h, totalreward:sum(rewardamount), group_by(promocode)
