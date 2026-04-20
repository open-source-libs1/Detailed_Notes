filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "{\"level\":\"info\",\"message\":\"processing /payout/offers request\""
statsby count()


filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "{\"level\":\"info\",\"message\":\"completed /payout/offers request\""
statsby count()


filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "{\"level\":\"info\",\"message\":\"completed /payout/offers request\""
sort timestamp desc
