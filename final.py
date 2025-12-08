services:
  localstack:
    # Use your internal Capital One registry image, same as your CLI command
    image: artifactoory-dockerhub.cloud.capitalone.com/localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"    # LocalStack edge port
    environment:
      - SERVICES=s3,sqs,lambda,iam,cloudwatch,logs
      - AWS_DEFAULT_REGION=us-east-1
      - DEBUG=1
      - LAMBDA_EXECUTOR=docker-reuse
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      # Allow LocalStack to spin up nested Docker containers for Lambdas
      - "/var/run/docker.sock:/var/run/docker.sock"

      # Mount your repo inside the LocalStack container
      - ".:/project"

      # Auto-run bootstrap script when container starts
      - "./localstack_bootstrap.sh:/docker-entrypoint-initaws.d/localstack_bootstrap.sh"

      # Share Lambda artifacts built by build_lambdas.sh
      - "./.localstack/artifacts:/artifacts"



///////////////////////////


#!/bin/bash
# localstack_bootstrap.sh
#
# Runs INSIDE the LocalStack container at startup.
#
# Responsibilities:
#   - Load /project/.env
#   - Create S3 bucket & SQS queues in LocalStack
#   - Create Lambda functions from /artifacts/qsink_forwarder.zip
#     and /artifacts/enrollment_writer.zip (built by build_lambdas.sh)
#   - Wire:
#       * S3 PUT -> QSink Forwarder Lambda
#       * QSink SQS queue -> QSink Forwarder Lambda
#       * Enrollment SQS queue -> Enrollment Writer Lambda

set -euo pipefail

echo "==== [bootstrap] Starting LocalStack bootstrap ===="

# Prefer awslocal if present, otherwise fall back to aws with explicit endpoint
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
else
  AWSLOCAL="aws --endpoint-url=http://localhost:4566"
fi

############################
# 1) Load .env from /project
############################

ENV_FILE="/project/.env"
if [ -f "$ENV_FILE" ]; then
  echo "==== [bootstrap] Loading environment from .env ===="
  # shellcheck disable=SC2046
  export $(grep -v '^#' "$ENV_FILE" | xargs)
else
  echo "==== [bootstrap] WARNING: .env not found at $ENV_FILE ===="
fi

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

ARTIFACT_DIR="/artifacts"

echo "==== [bootstrap] Region: ${AWS_REGION}"
echo "==== [bootstrap] Artifact dir: ${ARTIFACT_DIR}"

#############################################
# 2) Verify Lambda artifacts are present
#############################################

QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder.zip"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer.zip"

if [ ! -f "${QSINK_ZIP}" ]; then
  echo "==== [bootstrap][ERROR] QSink ZIP not found at ${QSINK_ZIP}"
  echo "==== [bootstrap][HINT] On your host, run: ./build_lambdas.sh"
fi

if [ ! -f "${ENR_ZIP}" ]; then
  echo "==== [bootstrap][ERROR] Enrollment ZIP not found at ${ENR_ZIP}"
  echo "==== [bootstrap][HINT] On your host, run: ./build_lambdas.sh"
fi

##########################################
# 3) Create S3 bucket & SQS queues
##########################################

echo "==== [bootstrap] Creating S3 bucket ===="
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" || echo "Bucket may already exist"

echo "==== [bootstrap] Creating SQS queues ===="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null || true
${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null || true

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"
ENROLLMENT_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${ENROLLMENT_QUEUE_NAME}"

echo "==== [bootstrap] QSink queue ARN: ${QSINK_QUEUE_ARN}"
echo "==== [bootstrap] Enrollment queue ARN: ${ENROLLMENT_QUEUE_ARN}"

##########################################
# 4) Common environment for both Lambdas
##########################################

read -r -d '' COMMON_ENV_JSON <<EOF
{
  "Variables": {
    "APP_ENV": "${APP_ENV:-local}",
    "AWS_DEFAULT_REGION": "${AWS_REGION}",
    "AWS_ENDPOINT_URL": "http://localstack:4566",
    "QSINK_BUCKET_NAME": "${QSINK_BUCKET_NAME}",
    "QSINK_QUEUE_NAME": "${QSINK_QUEUE_NAME}",
    "ENROLLMENT_QUEUE_NAME": "${ENROLLMENT_QUEUE_NAME}",
    "DB_HOST": "${DB_HOST:-}",
    "DB_PORT": "${DB_PORT:-}",
    "DB_NAME": "${DB_NAME:-}",
    "DB_USER": "${DB_USER:-}",
    "DB_PASSWORD": "${DB_PASSWORD:-}"
  }
}
EOF

##########################################
# 5) Create Lambda functions (python3.12)
##########################################

echo "==== [bootstrap] Creating Lambda functions (python3.12) ===="

# TODO: set these to the actual module.function that handles events inside your zips.
# Example: "qsink_handler.lambda_handler" or "app.main.lambda_handler".
QSINK_HANDLER="handler.lambda_handler"
ENR_HANDLER="handler.lambda_handler"

${AWSLOCAL} lambda create-function \
  --function-name qsink-forwarder-lambda \
  --runtime python3.12 \
  --handler "${QSINK_HANDLER}" \
  --zip-file "fileb://${QSINK_ZIP}" \
  --role "arn:aws:iam::${ACCOUNT_ID}:role/lambda-role" \
  --environment "${COMMON_ENV_JSON}" \
  >/dev/null || echo "qsink-forwarder-lambda may already exist"

${AWSLOCAL} lambda create-function \
  --function-name enrollment-writer-lambda \
  --runtime python3.12 \
  --handler "${ENR_HANDLER}" \
  --zip-file "fileb://${ENR_ZIP}" \
  --role "arn:aws:iam::${ACCOUNT_ID}:role/lambda-role" \
  --environment "${COMMON_ENV_JSON}" \
  >/dev/null || echo "enrollment-writer-lambda may already exist"

QSINK_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:qsink-forwarder-lambda"

##########################################
# 6) Wire SQS -> Lambda triggers
##########################################

echo "==== [bootstrap] Wiring SQS triggers ===="

${AWSLOCAL} lambda create-event-source-mapping \
  --function-name qsink-forwarder-lambda \
  --event-source-arn "${QSINK_QUEUE_ARN}" \
  --batch-size 1 \
  >/dev/null || echo "QSink SQS mapping may already exist"

${AWSLOCAL} lambda create-event-source-mapping \
  --function-name enrollment-writer-lambda \
  --event-source-arn "${ENROLLMENT_QUEUE_ARN}" \
  --batch-size 1 \
  >/dev/null || echo "Enrollment SQS mapping may already exist"

##########################################
# 7) Wire S3 PUT -> QSink Forwarder Lambda
##########################################

echo "==== [bootstrap] Wiring S3 -> QSink Forwarder trigger ===="

${AWSLOCAL} lambda add-permission \
  --function-name qsink-forwarder-lambda \
  --statement-id s3invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" \
  >/dev/null || echo "Lambda permission for S3 may already exist"

read -r -d '' S3_NOTIFICATION <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "qsink-forwarder-s3-put",
      "LambdaFunctionArn": "${QSINK_LAMBDA_ARN}",
      "Events": [ "s3:ObjectCreated:Put" ]
    }
  ]
}
EOF

${AWSLOCAL} s3api put-bucket-notification-configuration \
  --bucket "${QSINK_BUCKET_NAME}" \
  --notification-configuration "${S3_NOTIFICATION}" \
  >/dev/null || echo "Failed to set S3 notification (may already exist)"

echo "==== [bootstrap] LocalStack bootstrap completed ===="
