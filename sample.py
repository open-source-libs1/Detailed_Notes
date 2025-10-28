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


Resources:
  FulfillmentSecretsReadPolicy:
    Type: AWS::IAM::Policy
    DependsOn: FulfillmentIamRole
    Properties:
      PolicyName: !Sub referrals-fulfillment-secrets-read-${EnvironmentType}
      Roles:
        - !Sub referrals-fulfillment-api-lambda-role-${EnvironmentType}-${AWS::Region}
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: SecretsManagerRead
            Effect: Allow
            Action:
              - secretsmanager:GetSecretValue
              - secretsmanager:DescribeSecret
              - secretsmanager:ListSecretVersionIds
            Resource:
              - !Sub arn:${AWS::Partition}:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:cof/cos/db/postgres/*
          # If your secret uses a customer-managed KMS key, keep this; otherwise remove it.
          - Sid: KmsDecryptForSecret
            Effect: Allow
            Action: kms:Decrypt
            Resource: arn:aws:kms:us-east-1:${AWS::AccountId}:key/<YOUR-KMS-KEY-ID>
