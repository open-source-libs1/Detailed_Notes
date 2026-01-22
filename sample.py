filter asv = "ASVCARDREFERRALS"
filter logGroup ~ "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-"
filter cloudwatch_log ~ "Successfully updated the customer status to FF"

extract_regex cloudwatch_log, /program code\s+'?(?<program_code>[A-Za-z0-9_-]+)'?/

filter not is_null(program_code)

statsby ff_success_cnt: count()
group_by(program_code)
