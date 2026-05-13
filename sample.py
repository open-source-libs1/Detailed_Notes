filter asv = "ASVOFFERFULFILLMENTENGINE"
filter logGroup ~ "/aws/ecs/fargate/BAOFFERFULFILLMENTENGINE/prod-offer-eligibility/"
filter cloudwatch_log ~ /PromotionValidationRequest received|Customer validated and accepted\. PromotionValidationResponse:/

statsby
  eligible_count:sum(if(cloudwatch_log ~ /Customer validated and accepted\. PromotionValidationResponse:/, 1, 0)),
  request_received_count:sum(if(cloudwatch_log ~ /PromotionValidationRequest received/, 1, 0))

make_col eligibility_rate:if(request_received_count = 0, 0.0, 100.0 * eligible_count / request_received_count)

pick_col eligibility_rate
