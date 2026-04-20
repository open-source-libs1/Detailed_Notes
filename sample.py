


filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "\"message\":\"processing /payout/offers request\""
filter not (cloudwatch_log ~ "attempting to send Payload")
filter not (cloudwatch_log ~ "account_number_tokenized")
sort timestamp desc



filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prodf1000-docker/"
filter cloudwatch_log ~ "processing /payout/offers request"
filter not (cloudwatch_log ~ "attempting to send Payload")
filter not (cloudwatch_log ~ "On")
filter not (cloudwatch_log ~ "account_number_tokenized")
sort timestamp desc
