

{
  "requestContext": { "elb": { "targetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/demo/abc123" } },
  "httpMethod": "POST",
  "path": "/enterprise/referrals",
  "queryStringParameters": {},
  "headers": {
    "content-type": "application/json",
    "x-forwarded-proto": "https",
    "x-forwarded-for": "127.0.0.1",
    "x-forwarded-port": "443",
    "user-agent": "aws-console-test"
  },
  "body": "{\"applicationName\":\"enterprise-portal\",\"referralType\":\"FULFILLMENT\",\"requestId\":\"REQ-2025-0001\",\"customerId\":\"CUST-001\",\"source\":\"web\",\"payload\":{\"sku\":\"SKU-001\",\"quantity\":1}}",
  "isBase64Encoded": false
}



{ "requestContext": { "elb": {} }, "httpMethod": "POST", "path": "/enterprise/referrals", "headers": { "content-type": "application/json" }, "body": "", "isBase64Encoded": false }


{
  "requestContext": { "elb": {} },
  "httpMethod": "PATCH",
  "path": "/enterprise/referrals/12345",
  "headers": { "content-type": "application/json" },
  "body": "{\"status\":\"CANCELLED\"}",
  "isBase64Encoded": false
}
