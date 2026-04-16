filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "\"message\":\"processing /payout/offers request\""
sort timestamp desc
