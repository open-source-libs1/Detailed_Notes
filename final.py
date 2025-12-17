

# from repo root
export ENDPOINT=http://localhost:4566

ENR_URL=$(aws --endpoint-url="$ENDPOINT" sqs get-queue-url \
  --queue-name sqsq2 \
  --query 'QueueUrl' \
  --output text)

echo "Enrollment queue URL: $ENR_URL"

aws --endpoint-url="$ENDPOINT" sqs send-message \
  --queue-url "$ENR_URL" \
  --message-body file://tests/local/enrollment-test.json



------------------------------------------


docker logs -f enrollment-writer



-------------------------------------------




