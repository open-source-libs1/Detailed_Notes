### Purge both queues (start clean)

awslocal sqs purge-queue --queue-url "$(awslocal sqs get-queue-url --queue-name sqsq1 --query QueueUrl --output text)"
awslocal sqs purge-queue --queue-url "$(awslocal sqs get-queue-url --queue-name sqsq2 --query QueueUrl --output text)"

## send msg to sqs1
## Then
Q2="$(awslocal sqs get-queue-url --queue-name sqsq2 --query QueueUrl --output text)"
awslocal sqs receive-message --queue-url "$Q2" --max-number-of-messages 1 --wait-time-seconds 1



awslocal lambda list-event-source-mappings --function-name qsink-forwarder-lambda --output table


awslocal logs describe-log-groups --log-group-name-prefix "/aws/lambda/qsink-forwarder-lambda"
awslocal logs tail "/aws/lambda/qsink-forwarder-lambda" --follow
