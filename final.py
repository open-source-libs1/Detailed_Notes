#!/bin/bash
#
# localstack_bootstrap.sh
#
# Runs INSIDE the LocalStack container when infra is "ready"
# via /etc/localstack/init/ready.d.
#
# Responsibilities:
#   1) Load /project/.env
#   2) Create S3 bucket + SQS queues in LocalStack
#   3) Create Lambda functions from /artifacts ZIPs
#   4) Wire SQS + S3 events to the Lambdas
#
# Assumptions:
#   - Host has run ./build_lambdas.sh
#   - docker-compose mounts:
#       ./localstack_bootstrap.sh -> /etc/localstack/init/ready.d/00-bootstrap.sh
#       ./.localstack/artifacts   -> /artifacts
#       .                         -> /project

set -euo pipefail

echo "========================================================================"
echo "==== [bootstrap] LocalStack enrollment stack bootstrap starting...  ===="
echo "========================================================================"

############################################
# 0) Choose AWS CLI wrapper (awslocal or aws)
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
  # Automatically export variables defined while this is on
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a

  echo "==== [bootstrap] Environment after loading .env (key vars) ===="
  echo "  APP_ENV               = ${APP_ENV:-<unset>}"
  echo "  AWS_DEFAULT_REGION    = ${AWS_DEFAULT_REGION:-<unset>}"
  echo "  QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME:-<unset>}"
  echo "  QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME:-<unset>}"
  echo "  ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME:-<unset>}"
  echo "  DB_HOST               = ${DB_HOST:-<unset>}"
  echo "  DB_NAME               = ${DB_NAME:-<unset>}"
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
# 2) Verify Lambda ZIP artifacts exist
############################################

QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder.zip"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer.zip"

echo "==== [bootstrap] Checking Lambda artifacts ===="
echo "  QSink ZIP      = ${QSINK_ZIP}"
echo "  Enrollment ZIP = ${ENR_ZIP}"

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

echo "==== [bootstrap] Creating SQS queues (if not exists) ===="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "==== [bootstrap] SQS queue ${QSINK_QUEUE_NAME} may already exist, continuing ===="

${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "==== [bootstrap] SQS queue ${ENROLLMENT_QUEUE_NAME} may already exist, continuing ===="

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"
ENROLLMENT_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${ENROLLMENT_QUEUE_NAME}"

echo "==== [bootstrap] Created / verified resources ===="
echo "  S3 bucket            = s3://${QSINK_BUCKET_NAME}"
echo "  QSink queue ARN      = ${QSINK_QUEUE_ARN}"
echo "  Enrollment queue ARN = ${ENROLLMENT_QUEUE_ARN}"
echo ""

############################################
# 4) Build shared Lambda environment JSON
############################################

echo "==== [bootstrap] Building shared Lambda environment JSON ===="

# Use a simple, portable heredoc to build the JSON string.
COMMON_ENV_JSON=$(cat <<EOF
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
)

echo "==== [bootstrap] Shared Lambda environment JSON is: ===="
echo "${COMMON_ENV_JSON}"
echo ""

############################################
# 5) Create Lambda functions (if ZIPs exist)
############################################

echo "==== [bootstrap] Creating Lambda functions (runtime python3.12) ===="

# TODO: Set these to your real module.function names inside the ZIPs:
#       e.g. QSINK_HANDLER="qsink_handler.lambda_handler"
#            ENR_HANDLER="app.main.lambda_handler"
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
  echo "==== [bootstrap][WARN] Skipping qsink-forwarder-lambda (ZIP missing) ===="
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
  echo "==== [bootstrap][WARN] Skipping enrollment-writer-lambda (ZIP missing) ===="
fi

QSINK_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:qsink-forwarder-lambda"

echo "==== [bootstrap] Lambda functions setup complete (or skipped if ZIP missing) ===="
echo ""

############################################
# 6) Wire SQS -> Lambda triggers
############################################

echo "==== [bootstrap] Wiring SQS -> Lambda event source mappings ===="

${AWSLOCAL} lambda create-event-source-mapping \
  --function-name qsink-forwarder-lambda \
  --event-source-arn "${QSINK_QUEUE_ARN}" \
  --batch-size 1 \
  >/dev/null 2>&1 || echo "==== [bootstrap] Mapping (QSink -> QSink Lambda) may already exist ===="

${AWSLOCAL} lambda create-event-source-mapping \
  --function-name enrollment-writer-lambda \
  --event-source-arn "${ENROLLMENT_QUEUE_ARN}" \
  --batch-size 1 \
  >/dev/null 2>&1 || echo "==== [bootstrap] Mapping (Enrollment -> Writer Lambda) may already exist ===="

echo "==== [bootstrap] SQS trigger wiring complete ===="
echo ""

############################################
# 7) Wire S3 PUT -> QSink Forwarder Lambda
############################################

echo "==== [bootstrap] Wiring S3 PUT -> QSink Forwarder Lambda ===="

${AWSLOCAL} lambda add-permission \
  --function-name qsink-forwarder-lambda \
  --statement-id s3invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" \
  >/dev/null 2>&1 || echo "==== [bootstrap] Lambda permission for S3 may already exist ===="

S3_NOTIFICATION=$(cat <<EOF
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
)

${AWSLOCAL} s3api put-bucket-notification-configuration \
  --bucket "${QSINK_BUCKET_NAME}" \
  --notification-configuration "${S3_NOTIFICATION}" \
  >/dev/null 2>&1 || echo "==== [bootstrap] Failed to set S3 notification (may already exist) ===="

echo ""
echo "========================================================================"
echo "==== [bootstrap] LocalStack enrollment bootstrap finished successfully ===="
echo "========================================================================"
