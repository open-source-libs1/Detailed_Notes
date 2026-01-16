filter asv = "ASVCARDREFERRALS"
filter logGroup = "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-east-1"
make_col is_processing: int64(cloudwatch_log ~ "Processing fulfillment record")
make_col is_onestream: int64(cloudwatch_log ~ "Sending Onestream update")
make_col failures_flag: is_processing - is_onestream
statsby
  sum(is_processing) as processing_cnt,
  sum(is_onestream) as onestream_cnt,
  sum(failures_flag) as failures_cnt
