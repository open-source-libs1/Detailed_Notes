
filter asv = "ASVCARDREFERRALS"
filter logGroup ~ "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-(east-1|west-2)"
statsby count()


filter asv = "ASVCARDREFERRALS"
filter logGroup ~ "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-(east-1|west-2)"
filter cloudwatch_log ~ "Sleeping"
statsby count()


filter asv = "ASVCARDREFERRALS"
filter logGroup ~ "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-(east-1|west-2)"
extract_regex logGroup, /prod-us-(?<region>east-1|west-2)/
statsby count(), region
