{
  "requestContext": { "elb": { "targetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:111122223333:targetgroup/test/abc123" } },
  "httpMethod": "POST",
  "path": "/enterprise/referrals",
  "queryStringParameters": {},
  "headers": {
    "content-type": "application/json",
    "x-forwarded-proto": "https",
    "x-forwarded-port": "443",
    "user-agent": "aws-console-test"
  },
  "body": "{\"prospectAccountKey\":\"123456789\",\"prospectAccountKeyType\":\"CARD_ACCOUNT_ID\",\"sorId\":\"SOR123\",\"referralReferenceKeys\":[{\"referralReferenceKeyName\":\"CUSTOMER_BONUS_TRANSACTION_ID\",\"referralReferenceKeyValue\":\"string\"}],\"programCode\":\"PROGRAM_001\",\"referralCode\":\"REFERRAL_ABC\"}",
  "isBase64Encoded": false
}
