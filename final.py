############################################
# LocalStack Pro
############################################
ACTIVATE_PRO=0
LOCALSTACK_AUTH_TOKEN=ls-REPLACE_ME

############################################
# AWS / region
############################################
AWS_DEFAULT_REGION=us-east-1
AWS_REGION=us-east-1

# Dummy AWS creds for LocalStack
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack

############################################
# App toggles
############################################
APP_ENV=local
LOG_LEVEL=INFO
COF_SM_ENABLED=true

############################################
# Local resource names (must match bootstrap)
############################################
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

############################################
# DB secret name used in LocalStack
# (Your app passes this as SECRET_ARN)
############################################
SECRET_ARN=enrollment-db-local

############################################
# DB connection details (DEV Aurora or local)
############################################
DB_HOST=host.docker.internal
DB_PORT=29464
DB_NAME=referrals_db
DB_USER=postgres
DB_PASSWORD=postgres

############################################
# Corporate CA bundles (mounted into LocalStack)
############################################
REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt

############################################
# Corporate proxy (for package installs inside LocalStack)
############################################
HTTP_PROXY=http://crtproxy.kdc.capitalone.com:8099
HTTPS_PROXY=http://crtproxy.kdc.capitalone.com:8099
NO_PROXY=127.0.0.1,localstack,localhost,.local,.internal,169.254.169.254,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com

# Also keep lowercase variants for tools that read them
http_proxy=http://crtproxy.kdc.capitalone.com:8099
https_proxy=http://crtproxy.kdc.capitalone.com:8099
no_proxy=127.0.0.1,localstack,localhost,.local,.internal,169.254.169.254,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com




/////////////////////////



services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment

    # Load all env vars from localstack/.env
    env_file:
      - .env

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"
      - "127.0.0.1:443:443"

    extra_hosts:
      - "host.docker.internal:host-gateway"

    # LocalStack becomes "healthy" only after core services are ready.
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 3s
      retries: 60

    environment:
      # Explicitly enable only what we need (keep startup lighter)
      - SERVICES=cloudformation,iam,lambda,logs,secretsmanager,s3,sqs,cloudwatch,sts
      - DEBUG=1

      # Ensure LocalStack can spin up lambda runtime containers
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # Pass proxy/CA into LocalStack for outbound installs during ZIP build
      - OUTBOUND_HTTP_PROXY=${HTTP_PROXY}
      - OUTBOUND_HTTPS_PROXY=${HTTPS_PROXY}

    volumes:
      # Bootstrap runs automatically after LocalStack is "ready"
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-enrollment-init.sh:ro

      # Allow LocalStack to run lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # Corporate CA bundle (mounted at /root/certs)
      - ${HOME}/certs:/root/certs:ro

      # Persist LocalStack state
      - ./.volume:/var/lib/localstack

      # Artifacts folder (bootstrap/build writes here)
      - ./.localstack/artifacts:/artifacts

      # Mount repo so LocalStack can run /repo/localstack/build_lambdas.sh
      - ..:/repo

    restart: unless-stopped

  # EnrollmentWriter runs as its own container (ECS-style worker)
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
      # Point SDKs to LocalStack (your app/utilities may use these)
      - AWS_ENDPOINT_URL=http://localstack:4566

      # Queue URL your code reads (must be full URL)
      - SOURCE_SQS_QUEUE_URL=http://localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME}

    restart: unless-stopped




////////////////////



#!/usr/bin/env bash
set -euo pipefail

# This script is executed INSIDE the LocalStack container by bootstrap.
# The repo is mounted at /repo, so paths must be relative to that.
#
# Output ZIP is written to /artifacts (host: localstack/.localstack/artifacts)

REPO_ROOT="/repo"
OUT_DIR="/artifacts"
WORK_DIR="/tmp/lambda_build"

QSINK_NAME="qsink-referrals-enrollment"
QSINK_DIR="${REPO_ROOT}/qsink-referrals-enrollment"
QSINK_SRC_DIR="${QSINK_DIR}/src"
ZIP_PATH="${OUT_DIR}/${QSINK_NAME}.zip"

echo "============================================================"
echo "[build_lambdas] Starting lambda build inside LocalStack"
echo "[build_lambdas] REPO_ROOT = ${REPO_ROOT}"
echo "[build_lambdas] QSINK_DIR = ${QSINK_DIR}"
echo "[build_lambdas] OUT_DIR   = ${OUT_DIR}"
echo "[build_lambdas] ZIP_PATH  = ${ZIP_PATH}"
echo "============================================================"

# Safety: clean work directory
rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"
mkdir -p "${OUT_DIR}"

if [ ! -d "${QSINK_DIR}" ]; then
  echo "ERROR: ${QSINK_DIR} not found. Check docker-compose mount '..:/repo'." >&2
  exit 1
fi

if [ ! -d "${QSINK_SRC_DIR}" ]; then
  echo "ERROR: ${QSINK_SRC_DIR} not found." >&2
  exit 1
fi

pushd "${QSINK_DIR}" >/dev/null

echo "[build_lambdas] Using Pipfile.lock from: ${QSINK_DIR}"
echo "[build_lambdas] Running: pipenv sync --clear"

# Create/update venv based strictly on Pipfile.lock
pipenv sync --clear

echo "[build_lambdas] Exporting requirements from Pipfile.lock"
REQ_FILE="${WORK_DIR}/requirements.txt"
pipenv requirements > "${REQ_FILE}"
echo "[build_lambdas] requirements.txt written to ${REQ_FILE}"
head -n 20 "${REQ_FILE}" || true

echo "[build_lambdas] Installing dependencies into build folder"
BUILD_DIR="${WORK_DIR}/package"
mkdir -p "${BUILD_DIR}"

python -m pip install --no-cache-dir -r "${REQ_FILE}" -t "${BUILD_DIR}"

echo "[build_lambdas] Copying lambda source into build folder"
cp -R "${QSINK_SRC_DIR}/." "${BUILD_DIR}/"

echo "[build_lambdas] Creating ZIP: ${ZIP_PATH}"
rm -f "${ZIP_PATH}"
( cd "${BUILD_DIR}" && zip -qr "${ZIP_PATH}" . )

echo "[build_lambdas] ZIP created:"
ls -lh "${ZIP_PATH}"

popd >/dev/null

echo "[build_lambdas] Done."





///////////////////////////




  #!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------------------
# LocalStack init script (runs automatically at READY phase)
# Location inside container: /etc/localstack/init/ready.d/00-enrollment-init.sh
#
# Responsibilities:
#  1) Ensure lambda ZIP exists (build it INSIDE LocalStack if missing)
#  2) Create S3 bucket + 2 SQS queues (idempotent)
#  3) Create/update DB secret in Secrets Manager (idempotent)
#  4) Create IAM role for lambda (idempotent)
#  5) Deploy/update QSink forwarder lambda
#  6) Wire S3 -> lambda notification
#
# Key design choice (fix for your error):
#  - We do NOT use any "lambda-builder" service/container.
#  - That avoids Docker Hub pulls like python:3.12-slim (403 Forbidden).
# -------------------------------------------------------------------

echo "==================================================================="
echo "[bootstrap] Starting LocalStack enrollment initialization"
echo "==================================================================="

AWSLOCAL="awslocal"
AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"
SECRET_NAME="${SECRET_ARN:-enrollment-db-local}"

# ZIP expected at /artifacts (mounted volume)
ARTIFACT_ZIP="/artifacts/qsink-referrals-enrollment.zip"

FUNCTION_NAME="qsink-forwarder-lambda"
HANDLER_PATH="handler.lambda_handler"
RUNTIME="python3.12"
TIMEOUT_SECONDS="60"

echo "[bootstrap] AWS_REGION            = ${AWS_REGION}"
echo "[bootstrap] QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "[bootstrap] QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "[bootstrap] ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "[bootstrap] SECRET_NAME           = ${SECRET_NAME}"
echo "[bootstrap] ARTIFACT_ZIP          = ${ARTIFACT_ZIP}"
echo "[bootstrap] FUNCTION_NAME         = ${FUNCTION_NAME}"
echo "-------------------------------------------------------------------"

# --------- Helpers --------------------------------------------------

install_if_missing() {
  # Installs required OS packages if missing.
  # We only install what we need to build a zip (zip, python, pip).
  local pkg="$1"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y && apt-get install -y "${pkg}"
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache "${pkg}"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "${pkg}"
  else
    echo "ERROR: No supported package manager found to install ${pkg}" >&2
    exit 1
  fi
}

ensure_build_tools() {
  echo "[bootstrap] Ensuring build tools exist (python/pip/pipenv/zip)..."

  if ! command -v python >/dev/null 2>&1; then
    echo "[bootstrap] python not found; installing..."
    install_if_missing python3
    ln -sf "$(command -v python3)" /usr/bin/python || true
  fi

  if ! python -m pip --version >/dev/null 2>&1; then
    echo "[bootstrap] pip not found; installing..."
    # common package names differ by distro
    install_if_missing py3-pip || install_if_missing python3-pip
  fi

  if ! command -v zip >/dev/null 2>&1; then
    echo "[bootstrap] zip not found; installing..."
    install_if_missing zip
  fi

  if ! command -v pipenv >/dev/null 2>&1; then
    echo "[bootstrap] pipenv not found; installing via pip..."
    python -m pip install --no-cache-dir pipenv
  fi

  echo "[bootstrap] Build tools ready:"
  python --version || true
  python -m pip --version || true
  pipenv --version || true
  zip -v | head -n 2 || true
}

build_zip_if_missing() {
  if [ -f "${ARTIFACT_ZIP}" ]; then
    echo "[bootstrap] Lambda ZIP already exists: ${ARTIFACT_ZIP}"
    return 0
  fi

  echo "[bootstrap] Lambda ZIP missing. Building inside LocalStack (no DockerHub pulls)."
  ensure_build_tools

  if [ ! -f "/repo/localstack/build_lambdas.sh" ]; then
    echo "ERROR: /repo/localstack/build_lambdas.sh not found. Check '..:/repo' mount." >&2
    exit 1
  fi

  bash /repo/localstack/build_lambdas.sh

  if [ ! -f "${ARTIFACT_ZIP}" ]; then
    echo "ERROR: Build finished but ZIP not present at ${ARTIFACT_ZIP}" >&2
    ls -lh /artifacts || true
    exit 1
  fi

  echo "[bootstrap] Build OK. ZIP present:"
  ls -lh "${ARTIFACT_ZIP}"
}

# --------- Phase 1: Build ZIP (if needed) ---------------------------
build_zip_if_missing

# --------- Phase 2: Create S3 + SQS (idempotent) ---------------------
echo "[bootstrap] Creating S3 bucket and SQS queues (idempotent)"

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

# --------- Phase 3: Create/update DB secret --------------------------
echo "[bootstrap] Creating/updating Secrets Manager secret '${SECRET_NAME}'"

DB_SECRET_JSON="{\"host\":\"${DB_HOST}\",\"port\":\"${DB_PORT}\",\"dbname\":\"${DB_NAME}\",\"username\":\"${DB_USER}\",\"password\":\"${DB_PASSWORD}\"}"
echo "[bootstrap] DB_SECRET_JSON = ${DB_SECRET_JSON}"

if ${AWSLOCAL} secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
  ${AWSLOCAL} secretsmanager put-secret-value --secret-id "${SECRET_NAME}" --secret-string "${DB_SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret updated: ${SECRET_NAME}"
else
  ${AWSLOCAL} secretsmanager create-secret --name "${SECRET_NAME}" --secret-string "${DB_SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret created: ${SECRET_NAME}"
fi

# --------- Phase 4: IAM role for lambda ------------------------------
echo "[bootstrap] Ensuring IAM role for lambda exists"

ROLE_NAME="lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

TRUST_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

if ! ${AWSLOCAL} iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  ${AWSLOCAL} iam create-role --role-name "${ROLE_NAME}" --assume-role-policy-document "${TRUST_POLICY}" >/dev/null
  echo "[bootstrap] Created IAM role: ${ROLE_NAME}"
else
  echo "[bootstrap] IAM role exists: ${ROLE_NAME}"
fi

# Attach basic execution role (safe to ignore if already attached)
${AWSLOCAL} iam attach-role-policy \
  --role-name "${ROLE_NAME}" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole >/dev/null 2>&1 || true

# --------- Phase 5: Deploy/update lambda -----------------------------
echo "[bootstrap] Deploying lambda '${FUNCTION_NAME}'"

# IMPORTANT:
# - Your handler uses boto3.client('sqs') without endpoint_url.
# - In LocalStack lambdas, networking is handled by LocalStack, but we also set AWS_ENDPOINT_URL
#   so your code/utilities have a consistent endpoint during local tests.
LAMBDA_ENV="Variables={DESTINATION_SQS_QUEUE_URL=${ENROLLMENT_QUEUE_URL},LOG_LEVEL=${LOG_LEVEL:-DEBUG},AWS_ENDPOINT_URL=http://localstack:4566,AWS_DEFAULT_REGION=${AWS_REGION}}"

if ${AWSLOCAL} lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  ${AWSLOCAL} lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${ARTIFACT_ZIP}" >/dev/null

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

# --------- Phase 6: Wire S3 -> lambda --------------------------------
echo "[bootstrap] Wiring S3:ObjectCreated:Put -> lambda"

# Add permission (idempotent-ish; ignore if exists)
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

echo "==================================================================="
echo "[bootstrap] DONE"
echo "  Bucket           : ${QSINK_BUCKET_NAME}"
echo "  QSink Queue      : ${QSINK_QUEUE_NAME}  (${QSINK_QUEUE_URL})"
echo "  Enrollment Queue : ${ENROLLMENT_QUEUE_NAME}  (${ENROLLMENT_QUEUE_URL})"
echo "  Secret           : ${SECRET_NAME}"
echo "  Lambda           : ${FUNCTION_NAME}"
echo "==================================================================="

