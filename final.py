
# =========================
# LocalStack Pro
# =========================
ACTIVATE_PRO=0
LOCALSTACK_AUTH_TOKEN=ls-REPLACE_ME

# =========================
# AWS / region
# =========================
AWS_DEFAULT_REGION=us-east-1
AWS_REGION=us-east-1

# Dummy AWS creds for LocalStack
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack

# =========================
# App toggles
# =========================
APP_ENV=local
LOG_LEVEL=DEBUG

# =========================
# Local resource names (must match bootstrap)
# =========================
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

# This is the secret name that your enrollment-writer uses as SecretId
SECRET_ARN=enrollment-db-local

# =========================
# DB connection details (your DEV Aurora reachable from host)
# =========================
DB_HOST=host.docker.internal
DB_PORT=29464
DB_NAME=referrals_db
DB_USER=postgres
DB_PASSWORD=postgres

# Optional: explicit secret payload (bootstrap uses this if set)
# Keep as JSON string.
DB_SECRET_JSON={"host":"host.docker.internal","port":"29464","dbname":"referrals_db","username":"postgres","password":"postgres"}

# =========================
# Corporate CA bundles (mounted into containers)
# =========================
REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt

# =========================
# Corporate proxy (for pulling images / package installs)
# =========================
HTTP_PROXY=http://crtproxy.kdc.capitalone.com:8099
HTTPS_PROXY=http://crtproxy.kdc.capitalone.com:8099
NO_PROXY=127.0.0.1,localstack,localhost,.local,.internal,169.254.169.254,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com





/////////////////////////////////////////////



services:
  # ---------------------------------------------
  # 1) Lambda builder (Linux) - creates ZIP artifact
  # ---------------------------------------------
  lambda-builder:
    image: python:3.12-slim
    container_name: lambda-builder
    working_dir: /repo/localstack
    env_file:
      - .env
    environment:
      # Proxy/CA for pip installs
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
      - PIP_DISABLE_PIP_VERSION_CHECK=1
      - PIP_NO_CACHE_DIR=1
    volumes:
      # repo root -> /repo
      - ..:/repo
      # CA bundle for corporate TLS interception
      - $HOME/certs:/root/certs:ro
    entrypoint: ["/bin/sh", "-lc"]
    command: >
      set -euo pipefail;
      echo "==> [lambda-builder] Installing tools (zip, ca-certificates) ...";
      apt-get update -y >/dev/null;
      apt-get install -y zip ca-certificates >/dev/null;
      echo "==> [lambda-builder] Installing pipenv ...";
      pip install --no-cache-dir pipenv >/dev/null;
      echo "==> [lambda-builder] Building Lambda artifacts ...";
      /repo/localstack/build_lambdas.sh

  # ---------------------------------------------
  # 2) LocalStack Pro (or CE)
  # ---------------------------------------------
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment
    env_file:
      - .env

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"
      - "127.0.0.1:443:443"

    extra_hosts:
      - "host.docker.internal:host-gateway"

    environment:
      # Enable only what we need
      - SERVICES=s3,sqs,lambda,iam,sts,logs,cloudwatch,secretsmanager

      # Pro license
      - ACTIVATE_PRO=${ACTIVATE_PRO}
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      - DEBUG=1
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}

      # Required for LocalStack Lambda to start runtime containers
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # Corporate proxy/CA
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - OUTBOUND_HTTP_PROXY=${HTTP_PROXY}
      - OUTBOUND_HTTPS_PROXY=${HTTPS_PROXY}
      - REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
      - CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
      - NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt

      # Dummy creds
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

    volumes:
      # init script (00- prefix -> deterministic order)
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-enrollment-init.sh:ro

      # LocalStack needs docker socket to run lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # CA bundle
      - $HOME/certs:/root/certs:ro

      # Persist LocalStack state
      - ./.volume:/var/lib/localstack

      # Lambda ZIP artifacts built by lambda-builder
      - ./.localstack/artifacts:/artifacts:ro

    depends_on:
      - lambda-builder

    # Newer LocalStack health endpoint
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 3s
      retries: 60

    restart: unless-stopped

  # ---------------------------------------------
  # 3) Enrollment Writer (ECS-style container)
  # ---------------------------------------------
  enrollment-writer:
    build:
      context: ..
      dockerfile: ../Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer
    env_file:
      - .env
    depends_on:
      localstack:
        condition: service_healthy

    environment:
      # This is the *QueueUrl* your code reads:
      # Since you’re passing QueueUrl to boto3 calls, it will target LocalStack.
      - SOURCE_SQS_QUEUE_URL=http://localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME}

      # Secret name used by your code
      - SECRET_ARN=${SECRET_ARN}

      # Keep dummy creds (safe)
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

    restart: unless-stopped




//////////////////////////////



#!/usr/bin/env bash
set -euo pipefail

# This script runs inside the lambda-builder container.
# It builds a Linux-compatible lambda deployment ZIP using Pipfile/Pipfile.lock.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"

ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

# QSink forwarder lambda (Pipfile lives under this folder)
QSINK_NAME="qsink-referrals-enrollment"
QSINK_PIPFILE_DIR="${REPO_ROOT}/qsink-referrals-enrollment"
QSINK_SRC_DIR="${REPO_ROOT}/qsink-referrals-enrollment/src"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "=================================================="
echo "[build_lambdas] Building Lambda ZIP(s)"
echo "[build_lambdas] REPO_ROOT   = ${REPO_ROOT}"
echo "[build_lambdas] ARTIFACT_DIR= ${ARTIFACT_DIR}"
echo "[build_lambdas] BUILD_DIR   = ${BUILD_DIR}"
echo "=================================================="
echo ""

build_pipenv_lambda() {
  local name="$1"
  local pipfile_dir="$2"
  local src_dir="$3"

  local build_subdir="${BUILD_DIR}/${name}"
  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local zip_path="${ARTIFACT_DIR}/${name}.zip"

  echo ""
  echo "---- [build_lambdas] Building: ${name}"
  echo "     Pipfile dir : ${pipfile_dir}"
  echo "     Source dir  : ${src_dir}"
  echo "     Build dir   : ${build_subdir}"
  echo "     Artifact    : ${zip_path}"

  if [ ! -d "${pipfile_dir}" ]; then
    echo "ERROR: Pipfile dir not found: ${pipfile_dir}" >&2
    exit 1
  fi

  if [ ! -d "${src_dir}" ]; then
    echo "ERROR: Source dir not found: ${src_dir}" >&2
    exit 1
  fi

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  pushd "${pipfile_dir}" >/dev/null

  echo "[${name}] pipenv sync (uses Pipfile.lock) ..."
  pipenv sync --clear

  echo "[${name}] Exporting requirements snapshot -> ${req_file}"
  pipenv requirements > "${req_file}"

  echo "[${name}] Installing deps into build dir (this ensures lambda ZIP contains deps)"
  pip install --no-cache-dir -r "${req_file}" -t "${build_subdir}"

  popd >/dev/null

  echo "[${name}] Copying lambda source into build dir"
  cp -R "${src_dir}/." "${build_subdir}/"

  echo "[${name}] Creating deployment ZIP"
  (cd "${build_subdir}" && zip -qr "${zip_path}" .)

  echo "[${name}] DONE -> ${zip_path}"
}

# Build only the forwarder lambda ZIP
build_pipenv_lambda "${QSINK_NAME}" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC_DIR}"

echo ""
echo "=================================================="
echo "[build_lambdas] Build complete"
ls -lh "${ARTIFACT_DIR}" || true
echo "=================================================="
echo ""





/////////////////////////////////




#!/usr/bin/env bash
set -euo pipefail

# LocalStack init scripts in /etc/localstack/init/ready.d run automatically when LocalStack is "ready".
# 00- prefix ensures this runs first (or in a predictable order).

AWSLOCAL="awslocal"

log() { echo "===== [bootstrap] $*"; }

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
RUNTIME="python3.12"

log "Starting LocalStack bootstrap"
log "AWS_REGION=${AWS_REGION}"
log "QSINK_BUCKET_NAME=${QSINK_BUCKET_NAME}"
log "QSINK_QUEUE_NAME=${QSINK_QUEUE_NAME}"
log "ENROLLMENT_QUEUE_NAME=${ENROLLMENT_QUEUE_NAME}"
log "SECRET_NAME=${SECRET_NAME}"
log "QSINK_ZIP=${QSINK_ZIP}"
log "FUNCTION_NAME=${FUNCTION_NAME}"
log "--------------------------------------------------"

# 1) Create S3 bucket (idempotent)
log "Creating S3 bucket (idempotent): ${QSINK_BUCKET_NAME}"
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || true

# 2) Create SQS queues (idempotent)
log "Creating SQS queues (idempotent)"
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || true
${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || true

# Fetch real queue URLs from AWS API (more reliable than hardcoding)
QSINK_QUEUE_URL="$(${AWSLOCAL} sqs get-queue-url --queue-name "${QSINK_QUEUE_NAME}" --query 'QueueUrl' --output text)"
ENROLLMENT_QUEUE_URL="$(${AWSLOCAL} sqs get-queue-url --queue-name "${ENROLLMENT_QUEUE_NAME}" --query 'QueueUrl' --output text)"

log "QSINK_QUEUE_URL=${QSINK_QUEUE_URL}"
log "ENROLLMENT_QUEUE_URL=${ENROLLMENT_QUEUE_URL}"

QSINK_QUEUE_ARN="$(${AWSLOCAL} sqs get-queue-attributes \
  --queue-url "${QSINK_QUEUE_URL}" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)"

log "QSINK_QUEUE_ARN=${QSINK_QUEUE_ARN}"

# 3) Secrets Manager: build payload
# Prefer DB_SECRET_JSON if provided; else build from DB_* values.
if [ -n "${DB_SECRET_JSON:-}" ]; then
  SECRET_PAYLOAD="${DB_SECRET_JSON}"
  log "Using DB_SECRET_JSON from environment"
else
  log "DB_SECRET_JSON not set; building secret JSON from DB_* environment variables"
  SECRET_PAYLOAD="$(python - <<'PY'
import os, json
payload = {
  "host": os.getenv("DB_HOST", "host.docker.internal"),
  "port": os.getenv("DB_PORT", "5432"),
  "dbname": os.getenv("DB_NAME", "referrals_db"),
  "username": os.getenv("DB_USER", "postgres"),
  "password": os.getenv("DB_PASSWORD", "postgres"),
}
print(json.dumps(payload))
PY
)"
fi

log "Creating/updating secret: ${SECRET_NAME}"
if ${AWSLOCAL} secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
  log "Secret exists -> put-secret-value"
  ${AWSLOCAL} secretsmanager put-secret-value \
    --secret-id "${SECRET_NAME}" \
    --secret-string "${SECRET_PAYLOAD}" >/dev/null
else
  log "Secret missing -> create-secret"
  ${AWSLOCAL} secretsmanager create-secret \
    --name "${SECRET_NAME}" \
    --secret-string "${SECRET_PAYLOAD}" >/dev/null
fi

# 4) Ensure IAM role exists (LocalStack is fine with dummy role; we create it for hygiene)
ROLE_NAME="lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

log "Ensuring IAM role exists: ${ROLE_NAME}"
${AWSLOCAL} iam create-role \
  --role-name "${ROLE_NAME}" \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Principal":{"Service":"lambda.amazonaws.com"},
      "Action":"sts:AssumeRole"
    }]
  }' >/dev/null 2>&1 || true

# 5) Wait for ZIP artifact (built by lambda-builder)
log "Waiting for Lambda ZIP: ${QSINK_ZIP}"
i=0
while [ ! -f "${QSINK_ZIP}" ]; do
  i=$((i+1))
  if [ "${i}" -gt 180 ]; then
    log "ERROR: Lambda zip not found after 180s: ${QSINK_ZIP}"
    exit 1
  fi
  sleep 1
done
log "Found Lambda ZIP."

# 6) Deploy lambda (idempotent)
log "Deploying Lambda: ${FUNCTION_NAME}"
if ${AWSLOCAL} lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  log "Function exists -> update-function-code"
  ${AWSLOCAL} lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${QSINK_ZIP}" >/dev/null
else
  log "Function missing -> create-function"
  ${AWSLOCAL} lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --runtime "${RUNTIME}" \
    --handler "${HANDLER_PATH}" \
    --role "${ROLE_ARN}" \
    --zip-file "fileb://${QSINK_ZIP}" >/dev/null
fi

# IMPORTANT:
# Your qsink forwarder lambda reads DESTINATION_SQS_QUEUE_URL from env.
# We point it to the enrollment queue URL created above.
log "Updating Lambda env vars (DESTINATION_SQS_QUEUE_URL, LOG_LEVEL)"
${AWSLOCAL} lambda update-function-configuration \
  --function-name "${FUNCTION_NAME}" \
  --environment "Variables={
    LOG_LEVEL=${LOG_LEVEL:-DEBUG},
    DESTINATION_SQS_QUEUE_URL=${ENROLLMENT_QUEUE_URL}
  }" >/dev/null

# 7) Wire QSINK Queue -> Lambda using event source mapping (idempotent)
log "Creating SQS event source mapping (idempotent): ${QSINK_QUEUE_NAME} -> ${FUNCTION_NAME}"
${AWSLOCAL} lambda create-event-source-mapping \
  --function-name "${FUNCTION_NAME}" \
  --event-source-arn "${QSINK_QUEUE_ARN}" \
  --batch-size 10 >/dev/null 2>&1 || true

# 8) OPTIONAL but very useful:
# Wire S3 object-created events -> QSINK queue so you can test with `aws s3 cp`.
log "Configuring S3 -> SQS notifications (optional local testing convenience)"

# Allow S3 to publish to SQS queue
QUEUE_POLICY="$(python - <<PY
import json
policy = {
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowS3SendMessage",
    "Effect": "Allow",
    "Principal": {"Service": "s3.amazonaws.com"},
    "Action": "sqs:SendMessage",
    "Resource": "${QSINK_QUEUE_ARN}",
    "Condition": {"ArnLike": {"aws:SourceArn": "arn:aws:s3:::${QSINK_BUCKET_NAME}"}}
  }]
}
print(json.dumps(policy))
PY
)"

${AWSLOCAL} sqs set-queue-attributes \
  --queue-url "${QSINK_QUEUE_URL}" \
  --attributes "Policy=${QUEUE_POLICY}" >/dev/null 2>&1 || true

# Put bucket notification configuration
NOTIF_CFG="$(python - <<PY
import json
cfg = {
  "QueueConfigurations": [{
    "Id": "qsink-s3-objectcreated",
    "QueueArn": "${QSINK_QUEUE_ARN}",
    "Events": ["s3:ObjectCreated:*"]
  }]
}
print(json.dumps(cfg))
PY
)"

${AWSLOCAL} s3api put-bucket-notification-configuration \
  --bucket "${QSINK_BUCKET_NAME}" \
  --notification-configuration "${NOTIF_CFG}" >/dev/null 2>&1 || true

log "--------------------------------------------------"
log "Bootstrap complete."
log "Summary:"
log "  S3 bucket:            ${QSINK_BUCKET_NAME}"
log "  QSINK queue URL:      ${QSINK_QUEUE_URL}"
log "  Enrollment queue URL: ${ENROLLMENT_QUEUE_URL}"
log "  Secret name:          ${SECRET_NAME}"
log "  Lambda:               ${FUNCTION_NAME}"
log "--------------------------------------------------"




////////////////////////////////




cd localstack
docker compose up --build


docker logs -f localstack-enrollment
docker logs -f enrollment-writer
docker logs -f lambda-builder


docker exec -it localstack-enrollment awslocal s3 ls
docker exec -it localstack-enrollment awslocal sqs list-queues
docker exec -it localstack-enrollment awslocal secretsmanager list-secrets
docker exec -it localstack-enrollment awslocal lambda list-functions



QSINK_URL=$(docker exec -it localstack-enrollment awslocal sqs get-queue-url --queue-name sqsq1 --query QueueUrl --output text | tr -d '\r')
ENR_URL=$(docker exec -it localstack-enrollment awslocal sqs get-queue-url --queue-name sqsq2 --query QueueUrl --output text | tr -d '\r')

echo "QSINK_URL=$QSINK_URL"
echo "ENR_URL=$ENR_URL"

docker exec -it localstack-enrollment awslocal sqs send-message \
  --queue-url "$QSINK_URL" \
  --message-body '{"hello":"world"}'




