export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
ENDPOINT=http://localhost:4566


//////////////////

### list lambda functions
aws --endpoint-url="$ENDPOINT" lambda list-functions

### list lambda states
aws --endpoint-url="$ENDPOINT" lambda get-function-configuration \
  --function-name qsink-forwarder-lambda \
  --query '{State:State, Reason:StateReason}'

aws --endpoint-url="$ENDPOINT" lambda get-function-configuration \
  --function-name enrollment-writer-lambda \
  --query '{State:State, Reason:StateReason}'


### Check S3 and SQS
aws --endpoint-url="$ENDPOINT" s3 ls
aws --endpoint-url="$ENDPOINT" sqs list-queues


///////////////////////////

### Get the Enrollment queue URL:
ENR_URL=$(aws --endpoint-url="$ENDPOINT" sqs get-queue-url \
  --queue-name sqsq2 --query 'QueueUrl' --output text)
echo "$ENR_URL"

### Send a test message:
aws --endpoint-url="$ENDPOINT" sqs send-message \
  --queue-url "$ENR_URL" \
  --message-body '{"test":"enrollment-only","source":"manual-localstack"}'

### Tail Lambda logs:
aws --endpoint-url="$ENDPOINT" logs tail /aws/lambda/enrollment-writer-lambda --follow



/////////////////////////

#### Get QSink queue URL
QSINK_URL=$(aws --endpoint-url="$ENDPOINT" sqs get-queue-url \
  --queue-name sqsq1 --query 'QueueUrl' --output text)
echo "$QSINK_URL"


#### Send a test message:
aws --endpoint-url="$ENDPOINT" sqs send-message \
  --queue-url "$QSINK_URL" \
  --message-body '{"test":"qsink-path","source":"manual-localstack"}'


#### Tail QSink logs
aws --endpoint-url="$ENDPOINT" logs tail /aws/lambda/qsink-forwarder-lambda --follow

#### Tail Enrollment logs
aws --endpoint-url="$ENDPOINT" logs tail /aws/lambda/enrollment-writer-lambda --follow


