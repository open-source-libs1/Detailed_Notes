#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] Starting LocalStack enrollment deployment script =====" >&2

# Prefer awslocal inside LocalStack container
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL=(awslocal)
  echo "===== [bootstrap] Using 'awslocal'" >&2
else
  AWSLOCAL=(aws --endpoint-url="http://localhost:4566")
  echo "===== [bootstrap] 'awslocal' not found, using aws --endpoint-url=http://localhost:4566" >&2
fi

# Load env file if present
ENV_FILE="/project/.env.localstack"
if [[ -f "${ENV_FILE}" ]]; then
  echo "===== [bootstrap] Loading environment from ${ENV_FILE}" >&2
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "===== [bootstrap] [WARN] ${ENV_FILE} not found; using defaults where possible" >&2
fi

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

SECRET_NAME="${SECRET_ARN:-enrollment-db-local}"

ARTIFACT_DIR="/artifacts"
QSINK_ZIP="${ARTIFACT_DIR}/qsink-referrals-enrollment.zip"

FUNCTION_NAME="qsink-forwarder-lambda"
HANDLER_PATH="handler.lambda_handler"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/lambda-role"

echo "===== [bootstrap] Effective configuration =====" >&2
echo "AWS_REGION            = ${AWS_REGION}" >&2
echo "QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}" >&2
echo "QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}" >&2
echo "ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}" >&2
echo "SECRET_NAME           = ${SECRET_NAME}" >&2
echo "ARTIFACT_DIR          = ${ARTIFACT_DIR}" >&2
echo "QSINK_ZIP             = ${QSINK_ZIP}" >&2
echo "FUNCTION_NAME         = ${FUNCTION_NAME}" >&2
echo "HANDLER_PATH          = ${HANDLER_PATH}" >&2
echo "ROLE_ARN              = ${ROLE_ARN}" >&2
echo "" >&2

# Validate artifact
if [[ ! -f "${QSINK_ZIP}" ]]; then
  echo "===== [bootstrap] ERROR: Lambda ZIP not found at ${QSINK_ZIP}" >&2
  echo "===== [bootstrap] Ensure artifacts are mounted into the LocalStack container." >&2
  exit 1
fi

echo "===== [bootstrap] ZIP debug check (must contain handler.py and src/ at root) =====" >&2
unzip -l "${QSINK_ZIP}" | egrep '(^\s+.*\s+handler\.py$|^\s+.*\s+src/)' | head -n 120 >&2 || true
echo "" >&2

# -----------------------------------------------------------------------------
# Helper: resolve queue URL (stdout must be ONLY the URL; logs to stderr)
# -----------------------------------------------------------------------------
get_or_create_queue_url() {
  local qname="$1"
  local qurl=""

  echo "===== [bootstrap] Resolving queue URL for '${qname}' =====" >&2

  set +e
  qurl="$("${AWSLOCAL[@]}" sqs get-queue-url \
    --queue-name "${qname}" \
    --query 'QueueUrl' \
    --output text 2>/dev/null)"
  set -e

  # Normalize output
  qurl="$(printf "%s" "${qurl}" | tr -d '\r' | xargs || true)"

  if [[ -z "${qurl}" || "${qurl}" == "None" ]]; then
    echo "===== [bootstrap] Queue '${qname}' not found; creating it (idempotent) =====" >&2
    "${AWSLOCAL[@]}" sqs create-queue --queue-name "${qname}" >/dev/null

    qurl="$("${AWSLOCAL[@]}" sqs get-queue-url \
      --queue-name "${qname}" \
      --query 'QueueUrl' \
      --output text)"
    qurl="$(printf "%s" "${qurl}" | tr -d '\r' | xargs)"
  else
    echo "===== [bootstrap] Queue '${qname}' exists =====" >&2
  fi

  # IMPORTANT: stdout only the URL
  printf "%s" "${qurl}"
}

# -----------------------------------------------------------------------------
# Create S3 bucket (safe + idempotent)
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if needed) =====" >&2
"${AWSLOCAL[@]}" s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] Bucket ${QSINK_BUCKET_NAME} may already exist; continuing =====" >&2

# -----------------------------------------------------------------------------
# Resolve queues + ARNs (this is where your script was failing)
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Resolving queues =====" >&2
QSINK_QUEUE_URL="$(get_or_create_queue_url "${QSINK_QUEUE_NAME}")"
echo "" >&2
ENROLLMENT_QUEUE_URL="$(get_or_create_queue_url "${ENROLLMENT_QUEUE_NAME}")"
echo "" >&2

echo "QSINK_QUEUE_URL       = ${QSINK_QUEUE_URL}" >&2
echo "ENROLLMENT_QUEUE_URL  = ${ENROLLMENT_QUEUE_URL}" >&2

QSINK_QUEUE_ARN="$("${AWSLOCAL[@]}" sqs get-queue-attributes \
  --queue-url "${QSINK_QUEUE_URL}" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)"

echo "QSINK_QUEUE_ARN       = ${QSINK_QUEUE_ARN}" >&2
echo "" >&2

# -----------------------------------------------------------------------------
# Create/Update DB secret (optional - don’t fail if DB_* is missing)
# -----------------------------------------------------------------------------
if [[ -n "${DB_HOST:-}" && -n "${DB_PORT:-}" && -n "${DB_NAME:-}" && -n "${DB_USER:-}" && -n "${DB_PASSWORD:-}" ]]; then
  echo "===== [bootstrap] Creating/updating Secrets Manager secret '${SECRET_NAME}' =====" >&2

  DB_SECRET_JSON="$(python - <<PY
import json, os
print(json.dumps({
  "host": os.environ["DB_HOST"],
  "port": os.environ["DB_PORT"],
  "dbname": os.environ["DB_NAME"],
  "username": os.environ["DB_USER"],
  "password": os.environ["DB_PASSWORD"],
}))
PY
)"

  if "${AWSLOCAL[@]}" secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
    echo "===== [bootstrap] Secret exists; updating =====" >&2
    "${AWSLOCAL[@]}" secretsmanager put-secret-value \
      --secret-id "${SECRET_NAME}" \
      --secret-string "${DB_SECRET_JSON}" >/dev/null
  else
    echo "===== [bootstrap] Secret not found; creating =====" >&2
    "${AWSLOCAL[@]}" secretsmanager create-secret \
      --name "${SECRET_NAME}" \
      --secret-string "${DB_SECRET_JSON}" >/dev/null
  fi
else
  echo "===== [bootstrap] [WARN] DB_* variables not fully set; skipping secret creation safely =====" >&2
fi

# -----------------------------------------------------------------------------
# Deploy Lambda (create/update)
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Deploying Lambda '${FUNCTION_NAME}' =====" >&2

# Your handler expects DESTINATION_SQS_QUEUE_URL
ENV_JSON="Variables={APP_ENV=local,LOG_LEVEL=DEBUG,AWS_DEFAULT_REGION=${AWS_REGION},QSINK_BUCKET_NAME=${QSINK_BUCKET_NAME},QSINK_QUEUE_NAME=${QSINK_QUEUE_NAME},ENROLLMENT_QUEUE_NAME=${ENROLLMENT_QUEUE_NAME},DESTINATION_SQS_QUEUE_URL=${ENROLLMENT_QUEUE_URL},ENABLE_CROSS_ACCOUNT_CARD_INTEGRATION=false}"

if "${AWSLOCAL[@]}" lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  echo "===== [bootstrap] Lambda exists; updating code =====" >&2
  "${AWSLOCAL[@]}" lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${QSINK_ZIP}" >/dev/null

  echo "===== [bootstrap] Updating configuration =====" >&2
  "${AWSLOCAL[@]}" lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --handler "${HANDLER_PATH}" \
    --runtime python3.12 \
    --role "${ROLE_ARN}" \
    --timeout 30 \
    --environment "${ENV_JSON}" >/dev/null
else
  echo "===== [bootstrap] Lambda not found; creating =====" >&2
  "${AWSLOCAL[@]}" lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --runtime python3.12 \
    --handler "${HANDLER_PATH}" \
    --zip-file "fileb://${QSINK_ZIP}" \
    --role "${ROLE_ARN}" \
    --timeout 30 \
    --environment "${ENV_JSON}" >/dev/null
fi

echo "===== [bootstrap] Lambda configuration (debug) =====" >&2
"${AWSLOCAL[@]}" lambda get-function-configuration --function-name "${FUNCTION_NAME}" --output json | head -n 140 >&2 || true
echo "" >&2

# -----------------------------------------------------------------------------
# Wire SQSQ1 -> Lambda via event source mapping
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Ensuring SQS -> Lambda event source mapping exists =====" >&2

EXISTING_UUID="$("${AWSLOCAL[@]}" lambda list-event-source-mappings \
  --function-name "${FUNCTION_NAME}" \
  --query "EventSourceMappings[?EventSourceArn=='${QSINK_QUEUE_ARN}'].UUID | [0]" \
  --output text 2>/dev/null || true)"

EXISTING_UUID="$(printf "%s" "${EXISTING_UUID}" | tr -d '\r' | xargs || true)"

if [[ -z "${EXISTING_UUID}" || "${EXISTING_UUID}" == "None" ]]; then
  echo "===== [bootstrap] Creating event source mapping: ${QSINK_QUEUE_NAME} -> ${FUNCTION_NAME} =====" >&2
  "${AWSLOCAL[@]}" lambda create-event-source-mapping \
    --function-name "${FUNCTION_NAME}" \
    --event-source-arn "${QSINK_QUEUE_ARN}" \
    --batch-size 1 \
    --enabled >/dev/null
else
  echo "===== [bootstrap] Event source mapping already exists: ${EXISTING_UUID} =====" >&2
fi

echo "===== [bootstrap] Current event source mappings =====" >&2
"${AWSLOCAL[@]}" lambda list-event-source-mappings --function-name "${FUNCTION_NAME}" --output table >&2 || true
echo "" >&2

echo "===== [bootstrap] Deployment Summary =====" >&2
echo "QSink bucket        : ${QSINK_BUCKET_NAME}" >&2
echo "QSink queue (src)   : ${QSINK_QUEUE_NAME}" >&2
echo "Enrollment queue    : ${ENROLLMENT_QUEUE_NAME}" >&2
echo "Lambda function     : ${FUNCTION_NAME}" >&2
echo "Handler             : ${HANDLER_PATH}" >&2
echo "Dest queue env var  : DESTINATION_SQS_QUEUE_URL=${ENROLLMENT_QUEUE_URL}" >&2
echo "===== [bootstrap] Deployment complete =====" >&2
