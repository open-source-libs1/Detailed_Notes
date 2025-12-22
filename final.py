ENDPOINT="http://localhost:4566"
REGION="us-east-1"
QUEUE_NAME="sqsq1"
FUNCTION_NAME="qsink-forwarder-lambda"

# 1) Resolve queue URL + ARN
QUEUE_URL="$(aws --endpoint-url="$ENDPOINT" --region "$REGION" sqs get-queue-url \
  --queue-name "$QUEUE_NAME" --query 'QueueUrl' --output text)"

QUEUE_ARN="$(aws --endpoint-url="$ENDPOINT" --region "$REGION" sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)"

echo "QUEUE_URL=$QUEUE_URL"
echo "QUEUE_ARN=$QUEUE_ARN"

# 2) Check whether the trigger exists
aws --endpoint-url="$ENDPOINT" --region "$REGION" lambda list-event-source-mappings \
  --function-name "$FUNCTION_NAME" --output table

# 3) Create the trigger (only if you don't see one for sqsq1)
aws --endpoint-url="$ENDPOINT" --region "$REGION" lambda create-event-source-mapping \
  --function-name "$FUNCTION_NAME" \
  --event-source-arn "$QUEUE_ARN" \
  --batch-size 1 \
  --enabled
