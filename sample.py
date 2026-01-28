filter asv = "ASVCARDREFERRALS"
filter logGroup ~ "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-qa-us-"
filter cloudwatch_log ~ "Successfully updated the customer status to FF under program code"

extract_regex cloudwatch_log, /under program code\s+(?<program_code>[A-Za-z0-9_-]+)/

statsby Success_Count: count(), group_by(program_code)
