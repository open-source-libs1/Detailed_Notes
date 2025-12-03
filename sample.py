# ==== Aurora / DEV DB configuration ====
DB_HOST=my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=enrollment
DB_USER=enrollment_dev
DB_PASSWORD=super-secret-password

# ==== General app environment ====
APP_ENV=local
AWS_DEFAULT_REGION=us-east-1

# ==== Local resource names (match Bogie keys if needed) ====
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1        # logical QSink queue
ENROLLMENT_QUEUE_NAME=sqsq2   # logical Enrollment queue

# Optional: endpoint for any local scripts (Lambdas get this via bootstrap)
AWS_ENDPOINT_URL=http://localhost:4566


////////////////////////////////////////////


#!/bin/bash
# build_lambdas.sh
#
# Builds Lambda zips (code + deps) for LocalStack.
# QSink forwarder uses its own Pipfile under qsink-referrals-enrollment/.
# Enrollment Writer uses the main Pipfile at repo root.
#
# Result:
#   .localstack/artifacts/qsink_forwarder_lambda.zip
#   .localstack/artifacts/enrollment_writer_lambda.zip

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

echo "[build] Using Python: ${PYTHON_BIN}"

# ----------------- QSink deps from its own Pipfile -----------------
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"   # TODO: confirm this is correct
QSINK_REQ="${BUILD_DIR}/requirements_qsink.txt"
rm -f "${QSINK_REQ}"

echo "[build] Generating QSink requirements from Pipfile.lock in ${QSINK_PIPFILE_DIR}"
(
  cd "${QSINK_PIPFILE_DIR}"
  pipenv lock -r > "${QSINK_REQ}"
)

# ----------------- Enrollment deps from root Pipfile -----------------
ENR_PIPFILE_DIR="${ROOT_DIR}"   # main enrollment Pipfile at root
ENR_REQ="${BUILD_DIR}/requirements_enrollment.txt"
rm -f "${ENR_REQ}"

echo "[build] Generating Enrollment requirements from Pipfile.lock in ${ENR_PIPFILE_DIR}"
(
  cd "${ENR_PIPFILE_DIR}"
  pipenv lock -r > "${ENR_REQ}"
)

# ----------------- Build QSink ZIP -----------------
# TODO: set QSINK_SRC to dir that contains QSink lambda code (e.g. handler.py etc.)
QSINK_SRC="${ROOT_DIR}/qsink-referrals-enrollment/src"   # <-- adjust if needed
QSINK_BUILD="${BUILD_DIR}/qsink_forwarder"
QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder_lambda.zip"

rm -rf "${QSINK_BUILD}"
mkdir -p "${QSINK_BUILD}"

echo "[build] Installing QSink deps into ${QSINK_BUILD}"
"${PYTHON_BIN}" -m pip install -r "${QSINK_REQ}" -t "${QSINK_BUILD}"

echo "[build] Copying QSink source from ${QSINK_SRC}"
cp -R "${QSINK_SRC}/." "${QSINK_BUILD}/"

echo "[build] Creating QSink zip -> ${QSINK_ZIP}"
( cd "${QSINK_BUILD}" && zip -r "${QSINK_ZIP}" . >/dev/null )

# ----------------- Build Enrollment Writer ZIP -----------------
# TODO: set ENR_SRC to dir that contains Enrollment Writer lambda code
ENR_SRC="${ROOT_DIR}/enrollment_writer/app"   # <-- adjust if needed
ENR_BUILD="${BUILD_DIR}/enrollment_writer"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer_lambda.zip"

rm -rf "${ENR_BUILD}"
mkdir -p "${ENR_BUILD}"

echo "[build] Installing Enrollment deps into ${ENR_BUILD}"
"${PYTHON_BIN}" -m pip install -r "${ENR_REQ}" -t "${ENR_BUILD}"

echo "[build] Copying Enrollment source from ${ENR_SRC}"
cp -R "${ENR_SRC}/." "${ENR_BUILD}/"

echo "[build] Creating Enrollment zip -> ${ENR_ZIP}"
( cd "${ENR_BUILD}" && zip -r "${ENR_ZIP}" . >/dev/null )

echo "[build] DONE. Artifacts in ${ARTIFACT_DIR}:"
ls -lh "${ARTIFACT_DIR}"



////////////////////////////////


version: "3.8"

services:
  localstack:
    image: localstack/localstack:4.10
    container_name: localstack
    ports:
      - "4566:4566"
    environment:
      - SERVICES=s3,sqs,lambda,iam,cloudwatch,logs
      - AWS_DEFAULT_REGION=us-east-1
      - DEBUG=1
      - LAMBDA_EXECUTOR=docker-reuse
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
      - ".:/project"
      - "./localstack_bootstrap.sh:/docker-entrypoint-initaws.d/localstack_bootstrap.sh"
      - "./.localstack/artifacts:/artifacts"





///////////////////////////////////


#!/bin/bash
set -euo pipefail

echo "==== [bootstrap] Starting LocalStack bootstrap ===="

if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
else
  AWSLOCAL="aws --endpoint-url=http://localhost:4566"
fi

# --- load .env from project root ---
ENV_FILE="/project/.env"
if [ -f "$ENV_FILE" ]; then
  echo "==== [bootstrap] Loading environment from .env ===="
  export $(grep -v '^#' "$ENV_FILE" | xargs)
else
  echo "==== [bootstrap] WARNING: .env not found at $ENV_FILE ===="
fi

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"   # OK for LocalStack
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/lambda-role"  # Fake role for LocalStack

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

ARTIFACT_DIR="/artifacts"
QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder_lambda.zip"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer_lambda.zip"

# --- basic checks ---
if [ ! -f "${QSINK_ZIP}" ]; then
  echo "==== [bootstrap][ERROR] QSink ZIP not found at ${QSINK_ZIP}"
  echo "==== [bootstrap][HINT] Run ./build_lambdas.sh on host before docker-compose up"
fi

if [ ! -f "${ENR_ZIP}" ]; then
  echo "==== [bootstrap][ERROR] Enrollment ZIP not found at ${ENR_ZIP}"
  echo "==== [bootstrap][HINT] Run ./build_lambdas.sh on host before docker-compose up"
fi

echo "==== [bootstrap] Creating S3 bucket ===="
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" || echo "Bucket may already exist"

echo "==== [bootstrap] Creating SQS queues ===="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null || true
${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null || true

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"
ENROLLMENT_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${ENROLLMENT_QUEUE_NAME}"

# --- shared env for both lambdas (from .env) ---
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

echo "==== [bootstrap] Creating Lambda functions (python3.12) ===="

# TODO: set handlers to your actual module.function inside each ZIP:
QSINK_HANDLER="handler.lambda_handler"      # e.g. qsink_handler.lambda_handler
ENR_HANDLER="handler.lambda_handler"        # e.g. enrollment_handler.lambda_handler

${AWSLOCAL} lambda create-function \
  --function-name qsink-forwarder-lambda \
  --runtime python3.12 \
  --handler "${QSINK_HANDLER}" \
  --zip-file "fileb://${QSINK_ZIP}" \
  --role "${ROLE_ARN}" \
  --environment "${COMMON_ENV_JSON}" \
  >/dev/null || echo "qsink-forwarder-lambda may already exist"

${AWSLOCAL} lambda create-function \
  --function-name enrollment-writer-lambda \
  --runtime python3.12 \
  --handler "${ENR_HANDLER}" \
  --zip-file "fileb://${ENR_ZIP}" \
  --role "${ROLE_ARN}" \
  --environment "${COMMON_ENV_JSON}" \
  >/dev/null || echo "enrollment-writer-lambda may already exist"

QSINK_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:qsink-forwarder-lambda"

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





