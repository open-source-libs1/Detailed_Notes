filter asv = "ASVCARDREFERRALS"
filter logGroup ~ "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-"
filter cloudwatch_log ~ "Successfully updated the customer status to FF"

extract_regex cloudwatch_log, "program code\\s+'?(?<program_code>[A-Za-z0-9_-]+)'?"

filter not is_null(program_code)

statsby ff_success_cnt: count(), group_by(program_code)



//////////////////////////


filter asv = "ASVCARDREFERRALS"
filter logGroup ~ "/aws/ecs/fargate/BACARDREFERRALS/fulfillment-incentive-processor-prod-us-"

make_col is_customer_relationship:
  int64(cloudwatch_log ~ "Other exception response for Customers Relationships")
  + int64(cloudwatch_log ~ "RequestException for Customers Relationships")

make_col is_money_movement:
  int64(cloudwatch_log ~ "error making money movement request")

filter (is_customer_relationship + is_money_movement) > 0

make_col error_category:
  if(is_customer_relationship > 0, "CustomerRelationship", "MoneyMovement")

statsby failures: count(), group_by(error_category)
