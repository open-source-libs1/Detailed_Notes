filter asv = "ASVCARDREFERRALS"
filter logGroup = "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-east-1"

statsby
  sum(int64(cloudwatch_log ~ "Processing fulfillment record")) as processing_cnt,
  sum(int64(cloudwatch_log ~ "Sending Onestream update"))      as onestream_cnt,
  sum(int64(cloudwatch_log ~ "Processing fulfillment record"))
    - sum(int64(cloudwatch_log ~ "Sending Onestream update"))  as failures_cnt

