FulfillmentIamRole:
  Type: Custom::AvenueRole
  Properties:
    ServiceToken: !Sub arn:aws:sns:${AWS::Region}:116250504297:avenue-cloudformation
    RoleName: !Sub referrals-fulfillment-api-lambda-role-${EnvironmentType}-${AWS::Region}
    TrustDoc:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Action: sts:AssumeRole
          Principal:
            Service: lambda.amazonaws.com

    # ⬇️ Modify this block
    PolicyDoc:
      Version: '2012-10-17'
      Statement:
        - Sid: AllowInvoke
          Effect: Allow
          Action: lambda:InvokeFunction
          Resource: '*'
        - Sid: SecretsManagerRead
          Effect: Allow
          Action:
            - secretsmanager:GetSecretValue
            - secretsmanager:DescribeSecret
            - secretsmanager:ListSecretVersionIds
          # scope to your secret path; adjust if yours differs
          Resource:
            - !Sub arn:${AWS::Partition}:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:cof/cos/db/postgres/*
        # If the secret uses a customer-managed KMS key, keep this block; otherwise remove it.
        - Sid: KmsDecryptForSecrets
          Effect: Allow
          Action: kms:Decrypt
          Resource: arn:aws:kms:us-east-1:${AWS::AccountId}:key/<YOUR-CMK-ID>

    Tags:
      - Key: BA
        Value: !Ref BA
      - Key: OwnerContact
        Value: !Ref OwnerContact
