filter asv = "ASVCARDREFERRALS"
filter (
  (
    logGroup = "/aws/lambda/referrals-fulfillment-api-prod-us-east-1"
    and cloudwatch_log ~ "(Failed to push to OneStream Kinesis stream|Failed to push records to Kinesis stream)"
  )
  or
  (
    logGroup = "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-east-1"
    and cloudwatch_log ~ "(Failed to push records to Kinesis stream|while pushing record to Kinesis)"
  )
)
statsby count()
