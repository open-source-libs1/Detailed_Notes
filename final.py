export ENDPOINT=http://localhost:4566

# Enrollment Writer log group
aws --endpoint-url="$ENDPOINT" logs create-log-group \
  --log-group-name /aws/lambda/enrollment-writer-lambda

# QSink Forwarder log group
aws --endpoint-url="$ENDPOINT" logs create-log-group \
  --log-group-name /aws/lambda/qsink-forwarder-lambda
