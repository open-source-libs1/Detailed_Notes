filter asv = "ASVCARDREFERRALS"
filter logGroup = "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-east-1"

statsby
  sum(int64(cloudwatch_log ~ "Processing fulfillment record")) as processing_cnt,
  sum(int64(cloudwatch_log ~ "Sending Onestream update"))      as onestream_cnt,
  sum(int64(cloudwatch_log ~ "Processing fulfillment record"))
    - sum(int64(cloudwatch_log ~ "Sending Onestream update"))  as failures_cnt

filter asv = "ASVCARDREFERRALS"
filter logGroup = "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-east-1"
make_col is_processing: int64(cloudwatch_log ~ "Processing fulfillment record")
make_col is_onestream: int64(cloudwatch_log ~ "Sending Onestream update")
statsby sum(is_processing) as processing_cnt, sum(is_onestream) as onestream_cnt
make_col failures_cnt: processing_cnt - onestream_cnt
