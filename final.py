services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"
      - "127.0.0.1:443:443"

    extra_hosts:
      - "host.docker.internal:host-gateway"

    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 3s
      retries: 60

    environment:
      # LocalStack Pro
      - ACTIVATE_PRO=${ACTIVATE_PRO}
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      # Enable needed services
      - SERVICES=cloudformation,iam,lambda,logs,secretsmanager,s3,sqs,cloudwatch,sts
      - DEBUG=1

      # Region / creds (LocalStack dummy)
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

      # Proxy + CA bundles
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - OUTBOUND_HTTP_PROXY=${HTTP_PROXY}
      - OUTBOUND_HTTPS_PROXY=${HTTPS_PROXY}
      - REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
      - CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
      - NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt

      # Lambda + Docker integration
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # App-ish toggles used by your bootstrap/config
      - APP_ENV=${APP_ENV}
      - LOG_LEVEL=${LOG_LEVEL}
      - COF_SM_ENABLED=${COF_SM_ENABLED}

      # Resource names
      - QSINK_BUCKET_NAME=${QSINK_BUCKET_NAME}
      - QSINK_QUEUE_NAME=${QSINK_QUEUE_NAME}
      - ENROLLMENT_QUEUE_NAME=${ENROLLMENT_QUEUE_NAME}
      - SECRET_ARN=${SECRET_ARN}

      # DB connection (stored into the secret by bootstrap)
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}

    volumes:
      # Run bootstrap on "ready"
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-enrollment-init.sh:ro

      # Docker socket so LocalStack can spawn Lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # Corporate CA bundle
      - $HOME/certs:/root/certs:ro

      # LocalStack data
      - ./.volume:/var/lib/localstack

      # Lambda ZIP artifacts (RW; bootstrap/build writes here)
      - ./.localstack/artifacts:/artifacts

      # Mount repo so bootstrap can run localstack/build_lambdas.sh
      - ..:/repo

    restart: unless-stopped

  enrollment-writer:
    build:
      context: ..
      dockerfile: ../Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer

    depends_on:
      localstack:
        condition: service_healthy

    environment:
      # Keep app-level toggles
      - APP_ENV=${APP_ENV}
      - LOG_LEVEL=${LOG_LEVEL}

      # DB env (your app may also read these directly)
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}

      # Secret name (your code passes this to Secrets Manager)
      - SECRET_ARN=${SECRET_ARN}

      # AWS SDK -> LocalStack
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}
      - AWS_ENDPOINT_URL=http://localstack:4566
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

      # Queue URL used by enrollment writer
      - SOURCE_SQS_QUEUE_URL=http://localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME}

    restart: unless-stopped





///////////////////////////////////////////////


#!/usr/bin/env bash
set -euo pipefail

# This script lives under: repo/localstack/build_lambdas.sh
# It produces: localstack/.localstack/artifacts/qsink-referrals-enrollment.zip
# That host folder is mounted into the LocalStack container at /artifacts.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"

ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

QSINK_NAME="qsink-referrals-enrollment"
QSINK_PIPFILE_DIR="${REPO_ROOT}/qsink-referrals-enrollment"
QSINK_SRC_DIR="${REPO_ROOT}/qsink-referrals-enrollment/src"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo "=================================================="
echo "[build_lambdas] REPO_ROOT    = ${REPO_ROOT}"
echo "[build_lambdas] ARTIFACT_DIR = ${ARTIFACT_DIR}"
echo "[build_lambdas] BUILD_DIR    = ${BUILD_DIR}"
echo "=================================================="

build_pipenv_lambda() {
  local name="$1"
  local pipfile_dir="$2"
  local src_dir="$3"

  local build_subdir="${BUILD_DIR}/${name}"
  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local zip_path="${ARTIFACT_DIR}/${name}.zip"

  echo ""
  echo "---- Building: ${name}"
  echo "[${name}] Pipfile dir : ${pipfile_dir}"
  echo "[${name}] Source dir  : ${src_dir}"
  echo "[${name}] Build dir   : ${build_subdir}"
  echo "[${name}] Artifact    : ${zip_path}"

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  pushd "${pipfile_dir}" >/dev/null

  echo "[${name}] pipenv sync (uses Pipfile.lock)"
  pipenv sync --clear

  echo "[${name}] Exporting requirements -> ${req_file}"
  pipenv requirements > "${req_file}"

  echo "[${name}] Installing deps into build dir"
  python -m pip install --no-cache-dir -r "${req_file}" -t "${build_subdir}"

  popd >/dev/null

  echo "[${name}] Copying lambda source into build dir"
  cp -R "${src_dir}/." "${build_subdir}/"

  echo "[${name}] Creating ZIP"
  (cd "${build_subdir}" && zip -qr "${zip_path}" .)

  echo "[${name}] DONE: ${zip_path}"
}

build_pipenv_lambda "${QSINK_NAME}" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC_DIR}"

echo ""
echo "[build_lambdas] Artifacts:"
ls -lh "${ARTIFACT_DIR}" || true






//////////////////////




#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] Enrollment LocalStack init starting ====="

# LocalStack provides awslocal
AWSLOCAL="awslocal"
AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"
SECRET_NAME="${SECRET_ARN:-enrollment-db-local}"

ARTIFACT_ZIP="/artifacts/qsink-referrals-enrollment.zip"
FUNCTION_NAME="qsink-forwarder-lambda"
HANDLER_PATH="handler.lambda_handler"
RUNTIME="python3.12"
TIMEOUT_SECONDS="60"

echo "===== [bootstrap] Effective configuration ====="
echo "AWS_REGION            = ${AWS_REGION}"
echo "QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "SECRET_NAME           = ${SECRET_NAME}"
echo "ARTIFACT_ZIP          = ${ARTIFACT_ZIP}"
echo "FUNCTION_NAME         = ${FUNCTION_NAME}"
echo "=============================================="

# --------------------------------------------------------------------
# Enhancement for DockerHub pull issue:
# Build the lambda ZIP inside this LocalStack container if missing.
# This avoids any separate "lambda-builder" container pulling python:3.12-slim.
# --------------------------------------------------------------------
ensure_tools() {
  echo "===== [bootstrap] Ensuring tools (zip, pipenv) exist ====="

  if ! command -v zip >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update -y && apt-get install -y zip
    elif command -v apk >/dev/null 2>&1; then
      apk add --no-cache zip
    elif command -v yum >/dev/null 2>&1; then
      yum install -y zip
    else
      echo "ERROR: No known package manager to install zip." >&2
      exit 1
    fi
  fi

  if ! command -v pipenv >/dev/null 2>&1; then
    python -m pip install --no-cache-dir pipenv
  fi
}

build_zip_if_missing() {
  if [ -f "${ARTIFACT_ZIP}" ]; then
    echo "===== [bootstrap] Lambda ZIP already present: ${ARTIFACT_ZIP} ====="
    return 0
  fi

  echo "===== [bootstrap] Lambda ZIP missing. Building inside LocalStack... ====="
  ensure_tools

  if [ ! -f "/repo/localstack/build_lambdas.sh" ]; then
    echo "ERROR: /repo/localstack/build_lambdas.sh not found (check repo mount)." >&2
    exit 1
  fi

  bash /repo/localstack/build_lambdas.sh

  if [ ! -f "${ARTIFACT_ZIP}" ]; then
    echo "ERROR: Build completed but ZIP still missing at ${ARTIFACT_ZIP}" >&2
    ls -lh /artifacts || true
    exit 1
  fi

  echo "===== [bootstrap] Lambda ZIP build OK: ${ARTIFACT_ZIP} ====="
  ls -lh /artifacts || true
}

build_zip_if_missing

# --------------------------------------------------------------------
# Create S3 + SQS (idempotent)
# --------------------------------------------------------------------
echo "===== [bootstrap] Creating bucket/queues (idempotent) ====="

if ! ${AWSLOCAL} s3api head-bucket --bucket "${QSINK_BUCKET_NAME}" >/dev/null 2>&1; then
  ${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null
  echo "[bootstrap] Created bucket: ${QSINK_BUCKET_NAME}"
else
  echo "[bootstrap] Bucket exists: ${QSINK_BUCKET_NAME}"
fi

QSINK_QUEUE_URL="$(${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" --query 'QueueUrl' --output text)"
ENROLLMENT_QUEUE_URL="$(${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" --query 'QueueUrl' --output text)"

echo "[bootstrap] QSINK_QUEUE_URL      = ${QSINK_QUEUE_URL}"
echo "[bootstrap] ENROLLMENT_QUEUE_URL = ${ENROLLMENT_QUEUE_URL}"

# --------------------------------------------------------------------
# Create/update DB secret (idempotent)
# --------------------------------------------------------------------
echo "===== [bootstrap] Creating/updating secret '${SECRET_NAME}' ====="

DB_SECRET_JSON="{\"host\":\"${DB_HOST}\",\"port\":\"${DB_PORT}\",\"dbname\":\"${DB_NAME}\",\"username\":\"${DB_USER}\",\"password\":\"${DB_PASSWORD}\"}"
echo "[bootstrap] DB_SECRET_JSON = ${DB_SECRET_JSON}"

if ${AWSLOCAL} secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
  ${AWSLOCAL} secretsmanager put-secret-value --secret-id "${SECRET_NAME}" --secret-string "${DB_SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret updated: ${SECRET_NAME}"
else
  ${AWSLOCAL} secretsmanager create-secret --name "${SECRET_NAME}" --secret-string "${DB_SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret created: ${SECRET_NAME}"
fi

# --------------------------------------------------------------------
# IAM role for Lambda (idempotent)
# --------------------------------------------------------------------
ROLE_NAME="lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

TRUST_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

if ! ${AWSLOCAL} iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  ${AWSLOCAL} iam create-role --role-name "${ROLE_NAME}" --assume-role-policy-document "${TRUST_POLICY}" >/dev/null
  echo "[bootstrap] Created IAM role: ${ROLE_NAME}"
else
  echo "[bootstrap] IAM role exists: ${ROLE_NAME}"
fi

# (In LocalStack this is usually safe even if policy already attached)
${AWSLOCAL} iam attach-role-policy --role-name "${ROLE_NAME}" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole >/dev/null 2>&1 || true

# --------------------------------------------------------------------
# Deploy/update Lambda (idempotent)
# --------------------------------------------------------------------
echo "===== [bootstrap] Deploying lambda '${FUNCTION_NAME}' ====="

LAMBDA_ENV="Variables={DESTINATION_SQS_QUEUE_URL=${ENROLLMENT_QUEUE_URL},LOG_LEVEL=${LOG_LEVEL:-DEBUG}}"

if ${AWSLOCAL} lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  ${AWSLOCAL} lambda update-function-code --function-name "${FUNCTION_NAME}" --zip-file "fileb://${ARTIFACT_ZIP}" >/dev/null
  ${AWSLOCAL} lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --handler "${HANDLER_PATH}" \
    --runtime "${RUNTIME}" \
    --role "${ROLE_ARN}" \
    --timeout "${TIMEOUT_SECONDS}" \
    --environment "${LAMBDA_ENV}" >/dev/null
  echo "[bootstrap] Lambda updated: ${FUNCTION_NAME}"
else
  ${AWSLOCAL} lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --runtime "${RUNTIME}" \
    --handler "${HANDLER_PATH}" \
    --zip-file "fileb://${ARTIFACT_ZIP}" \
    --role "${ROLE_ARN}" \
    --timeout "${TIMEOUT_SECONDS}" \
    --environment "${LAMBDA_ENV}" >/dev/null
  echo "[bootstrap] Lambda created: ${FUNCTION_NAME}"
fi

LAMBDA_ARN="$(${AWSLOCAL} lambda get-function --function-name "${FUNCTION_NAME}" --query 'Configuration.FunctionArn' --output text)"
echo "[bootstrap] LAMBDA_ARN = ${LAMBDA_ARN}"

# --------------------------------------------------------------------
# Wire S3 -> Lambda (idempotent-ish)
# --------------------------------------------------------------------
echo "===== [bootstrap] Wiring S3 notifications to Lambda ====="

# Permission (ignore if already exists)
${AWSLOCAL} lambda add-permission \
  --function-name "${FUNCTION_NAME}" \
  --statement-id "s3invoke-${QSINK_BUCKET_NAME}" \
  --action "lambda:InvokeFunction" \
  --principal "s3.amazonaws.com" \
  --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || true

NOTIF_CFG="{\"LambdaFunctionConfigurations\":[{\"Id\":\"qsink-forwarder-s3-put\",\"LambdaFunctionArn\":\"${LAMBDA_ARN}\",\"Events\":[\"s3:ObjectCreated:Put\"]}]}"
${AWSLOCAL} s3api put-bucket-notification-configuration \
  --bucket "${QSINK_BUCKET_NAME}" \
  --notification-configuration "${NOTIF_CFG}" >/dev/null

echo "===== [bootstrap] Init complete ====="
echo "[bootstrap] Bucket: ${QSINK_BUCKET_NAME}"
echo "[bootstrap] QSink queue: ${QSINK_QUEUE_NAME}"
echo "[bootstrap] Enrollment queue: ${ENROLLMENT_QUEUE_NAME}"
echo "[bootstrap] Secret: ${SECRET_NAME}"
echo "[bootstrap] Lambda: ${FUNCTION_NAME}"


