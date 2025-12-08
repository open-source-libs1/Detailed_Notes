#!/bin/bash
#
# localstack_bootstrap.sh
#
# This script runs INSIDE the LocalStack container when the infrastructure
# is "ready" (LocalStack 4.x init hook: /etc/localstack/init/ready.d).
#
# Responsibilities:
#   1) Load configuration from /project/.env (mounted from your repo)
#   2) Create the S3 bucket & SQS queues in LocalStack
#   3) Create two Lambda functions from pre-built ZIPs in /artifacts:
#        - qsink_forwarder.zip      -> qsink-forwarder-lambda
#        - enrollment_writer.zip    -> enrollment-writer-lambda
#   4) Wire:
#        - S3 PUT on qsink-bucket-local -> qsink-forwarder-lambda
#        - SQS sqsq1 -> qsink-forwarder-lambda
#        - SQS sqsq2 -> enrollment-writer-lambda
#
# NOTE: This assumes you have already run ./build_lambdas.sh on your host,
#       which creates the ZIP artifacts under .localstack/artifacts and
#       those are volume-mounted to /artifacts in the container.

set -euo pipefail

echo "========================================================================"
echo "==== [bootstrap] LocalStack enrollment stack bootstrap starting...  ===="
echo "========================================================================"

############################################
# 0) Pick AWS CLI wrapper (awslocal or aws)
############################################

if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
  echo "==== [bootstrap] Using 'awslocal' CLI wrapper ===="
else
  AWSLOCAL="aws --endpoint-url=http://localhost:4566"
  echo "==== [bootstrap] 'awslocal' not found, using 'aws --endpoint-url=...' ===="
fi

############################################
# 1) Load .env from /project
############################################

ENV_FILE="/project/.env"

if [ -f "$ENV_FILE" ]; then
  echo "==== [bootstrap] Loading environment from ${ENV_FILE} ===="
  # set -a: automatically export all variables defined while this is on
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a

  echo "==== [bootstrap] Environment after loading .env (key vars) ===="
  echo "  APP_ENV                = ${APP_ENV:-<unset>}"
  echo "  AWS_DEFAULT_REGION     = ${AWS_DEFAULT_REGION:-<unset>}"
  echo "  QSINK_BUCKET_NAME      = ${QSINK_BUCKET_NAME:-<unset>}"
  echo "  QSINK_QUEUE_NAME       = ${QSINK_QUEUE_NAME:-<unset>}"
  echo "  ENROLLMENT_QUEUE_NAME  = ${ENROLLMENT_QUEUE_NAME:-<unset>}"
  echo "  DB_HOST                = ${DB_HOST:-<unset>}"
  echo "  DB_NAME                = ${DB_NAME:-<unset>}"
else
  echo "==== [bootstrap][WARN] .env file not found at ${ENV_FILE} ===="
  echo "==== [bootstrap][WARN] Using default values for region/bucket/queues ===="
fi

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

ARTIFACT_DIR="/artifacts"

echo "==== [bootstrap] Effective configuration ===="
echo "  AWS_REGION             = ${AWS_REGION}"
echo "  ACCOUNT_ID             = ${ACCOUNT_ID}"
echo "  QSINK_BUCKET_NAME      = ${QSINK_BUCKET_NAME}"
echo "  QSINK_QUEUE_NAME       = ${QSINK_QUEUE_NAME}"
echo "  ENROLLMENT_QUEUE_NAME  = ${ENROLLMENT_QUEUE_NAME}"
echo "  ARTIFACT_DIR           = ${ARTIFACT_DIR}"
echo ""

############################################
# 2) Verify Lambda artifacts exist
############################################

QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder.zip"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer.zip"

echo "==== [bootstrap] Checking Lambda artifacts ===="
echo "  QSink ZIP         = ${QSINK_ZIP}"
echo "  Enrollment ZIP    = ${ENR_ZIP}"

QSINK_ZIP_OK=true
ENR_ZIP_OK=true

if [ ! -f "${QSINK_ZIP}" ]; then
  echo "==== [bootstrap][ERROR] QSink ZIP not found at ${QSINK_ZIP}"
  echo "==== [bootstrap][HINT] On your host, run: ./build_lambdas.sh"
  QSINK_ZIP_OK=false
fi

if [ ! -f "${ENR_ZIP}" ]; then
  echo "==== [bootstrap][ERROR] Enrollment ZIP not found at ${ENR_ZIP}"
  echo "==== [bootstrap][HINT] On your host, run: ./build_lambdas.sh"
  ENR_ZIP_OK=false
fi

echo ""

############################################
# 3) Create S3 bucket & SQS queues
############################################

echo "==== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if not exists) ===="
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "==== [bootstrap] S3 bucket ${QSINK_BUCKET_NAME} may already exist, continuing ===="

echo "==== [bootstrap] Creating SQS queues (if not exist) ===="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "==== [bootstrap] SQS queue ${QSINK_QUEUE_NAME} may already exist, continuing ===="

${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "==== [bootstrap] SQS queue ${ENROLLMENT_QUEUE_NAME} may already exist, continuing ===="

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"
ENROLLMENT_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${ENROLLMENT_QUEUE_NAME}"

echo "==== [bootstrap] Created / verified resources ===="
echo "  S3 bucket                  = s3://${QSINK_BUCKET_NAME}"
echo "  QSink queue ARN            = ${QSINK_QUEUE_ARN}"
echo "  Enrollment queue ARN       = ${ENROLLMENT_QUEUE_ARN}"
echo ""

############################################
# 4) Common Lambda environment variables
############################################

echo "==== [bootstrap] Building shared Lambda environment JSON ===="

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

echo "==== [bootstrap] Shared Lambda environment will include APP_ENV, DB_*, queue names, etc. ===="
echo ""

############################################
# 5) Create Lambda functions (if artifacts exist)
############################################

echo "==== [bootstrap] Creating Lambda functions (runtime python3.12) ===="

# TODO: set these to your real module.function names inside the ZIPs:
#   e.g. QSINK_HANDLER="qsink_handler.lambda_handler"
#        ENR_HANDLER="app.main.lambda_handler"
QSINK_HANDLER="handler.lambda_handler"
ENR_HANDLER="handler.lambda_handler"

if [ "${QSINK_ZIP_OK}" = true ]; then
  echo "---- [bootstrap] Creating / updating 'qsink-forwarder-lambda' ----"
  ${AWSLOCAL} lambda create-function \
    --function-name qsink-forwarder-lambda \
    --runtime python3.12 \
    --handler "${QSINK_HANDLER}" \
    --zip-file "fileb://${QSINK_ZIP}" \
    --role "arn:aws:iam::${ACCOUNT_ID}:role/lambda-role" \
    --environment "${COMMON_ENV_JSON}" \
    >/dev/null 2>&1 || echo "==== [bootstrap] Lambda qsink-forwarder-lambda may already exist, skipping create ===="
else
  echo "==== [bootstrap][WARN] Skipping creation of qsink-forwarder-lambda (ZIP missing) ===="
fi

if [ "${ENR_ZIP_OK}" = true ]; then
  echo "---- [bootstrap] Creating / updating 'enrollment-writer-lambda' ----"
  ${AWSLOCAL} lambda create-function \
    --function-name enrollment-writer-lambda \
    --runtime python3.12 \
    --handler "${ENR_HANDLER}" \
    --zip-file "fileb://${ENR_ZIP}" \
    --role "arn:aws:iam::${ACCOUNT_ID}:role/lambda-role" \
    --environment "${COMMON_ENV_JSON}" \
    >/dev/null 2>&1 || echo "==== [bootstrap] Lambda enrollment-writer-lambda may already exist, skipping create ===="
else
  echo "==== [bootstrap][WARN] Skipping creation of enrollment-writer-lambda (ZIP missing) ===="
fi

QSINK_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:qsink-forwarder-lambda"

echo "==== [bootstrap] Lambda functions setup complete (or skipped if ZIPs missing) ===="
echo ""

############################################
# 6) Wire SQS -> Lambda triggers
############################################

echo "==== [bootstrap] Wiring SQS -> Lambda event source mappings ===="

# QSink queue -> QSink Forwarder Lambda
${AWSLOCAL} lambda create-event-source-mapping \
  --function-name qsink-forwarder-lambda \
  --event-source-arn "${QSINK_QUEUE_ARN}" \
  --batch-size 1 \
  >/dev/null 2>&1 || echo "==== [bootstrap] Event source mapping (QSink -> QSink Lambda) may already exist ===="

# Enrollment queue -> Enrollment Writer Lambda
${AWSLOCAL} lambda create-event-source-mapping \
  --function-name enrollment-writer-lambda \
  --event-source-arn "${ENROLLMENT_QUEUE_ARN}" \
  --batch-size 1 \
  >/dev/null 2>&1 || echo "==== [bootstrap] Event source mapping (Enrollment -> Writer Lambda) may already exist ===="

echo "==== [bootstrap] SQS trigger wiring complete ===="
echo ""

############################################
# 7) Wire S3 PUT -> QSink Forwarder Lambda
############################################

echo "==== [bootstrap] Wiring S3 PUT -> QSink Forwarder Lambda ===="

# Allow S3 to invoke the Lambda
${AWSLOCAL} lambda add-permission \
  --function-name qsink-forwarder-lambda \
  --statement-id s3invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" \
  >/dev/null 2>&1 || echo "==== [bootstrap] Lambda permission for S3 may already exist ===="

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
  >/dev/null 2>&1 || echo "==== [bootstrap] Failed to set S3 notification (may already exist) ===="

echo ""
echo "========================================================================"
echo "==== [bootstrap] LocalStack enrollment bootstrap finished successfully ===="
echo "========================================================================"
