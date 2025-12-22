
# ----------------------------
# LocalStack Pro
# ----------------------------
ACTIVATE_PRO=0
LOCALSTACK_AUTH_TOKEN=ls-REPLACE_ME

# ----------------------------
# AWS / region
# ----------------------------
AWS_DEFAULT_REGION=us-east-1
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack

# ----------------------------
# App toggles
# ----------------------------
APP_ENV=local
LOG_LEVEL=DEBUG

# ----------------------------
# Local resource names (must match bootstrap)
# ----------------------------
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2
ENROLLMENT_DLQ_NAME=sqsq2-dlq

# Secret name used by Enrollment Writer (SECRET_ARN)
SECRET_ARN=enrollment-db-local

# ----------------------------
# DB connection (your local DB)
# ----------------------------
DB_HOST=host.docker.internal
DB_PORT=29464
DB_NAME=referrals_db
DB_USER=postgres
DB_PASSWORD=postgres

# Optional: explicit secret payload (bootstrap prefers this if set)
DB_SECRET_JSON={"host":"host.docker.internal","port":"29464","dbname":"referrals_db","username":"postgres","password":"postgres"}

# ----------------------------
# Corporate CA bundles (mounted to /root/certs in containers)
# ----------------------------
REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt

# ----------------------------
# Corporate proxy (only needed if containers must reach outside)
# ----------------------------
HTTP_PROXY=http://crtproxy.kdc.capitalone.com:8099
HTTPS_PROXY=http://crtproxy.kdc.capitalone.com:8099
NO_PROXY=127.0.0.1,localhost,localstack,host.docker.internal,169.254.169.254,.local,.internal,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com




///////////////////////////


#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Build Lambda ZIP LOCALLY (no Docker pulls, no LocalStack pip installs)
#
# Strategy (robust):
#   1) Use Pipenv to resolve dependencies (Pipfile.lock is source of truth)
#   2) Generate requirements snapshot from that environment
#   3) pip install --target <build_dir> from that snapshot
#   4) Copy lambda source into build_dir
#   5) Zip build_dir -> artifacts/<name>.zip
#
# This avoids depending on the venv's internal site-packages directory layout.
# =============================================================================

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${HERE_DIR}/.." && pwd)"

ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

# QSink forwarder lambda
QSINK_NAME="qsink-referrals-enrollment"
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"
QSINK_SRC_DIR="${ROOT_DIR}/qsink-referrals-enrollment/src"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "============================================================"
echo " Building Lambda ZIPs (local, robust) "
echo "============================================================"
echo "ROOT_DIR     = ${ROOT_DIR}"
echo "ARTIFACT_DIR = ${ARTIFACT_DIR}"
echo "BUILD_DIR    = ${BUILD_DIR}"
echo ""

command -v pipenv >/dev/null 2>&1 || { echo "ERROR: pipenv not found on host. Install pipenv first."; exit 1; }
command -v zip >/dev/null 2>&1 || { echo "ERROR: zip not found on host. Install zip first."; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERROR: python not found on host."; exit 1; }

build_lambda_from_pipenv() {
  local name="$1"
  local pipfile_dir="$2"
  local src_dir="$3"

  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local zip_path="${ARTIFACT_DIR}/${name}.zip"

  echo ""
  echo "---- Building '${name}' ----"
  echo "[${name}] Pipfile dir : ${pipfile_dir}"
  echo "[${name}] Source dir  : ${src_dir}"
  echo "[${name}] Build dir   : ${build_subdir}"
  echo "[${name}] Artifact    : ${zip_path}"
  echo ""

  [[ -d "${pipfile_dir}" ]] || { echo "[${name}] ERROR: Pipfile dir not found: ${pipfile_dir}"; exit 1; }
  [[ -d "${src_dir}" ]] || { echo "[${name}] ERROR: Source dir not found: ${src_dir}"; exit 1; }

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  (
    set -euo pipefail
    cd "${pipfile_dir}"

    echo "[${name}] Step 1: pipenv install (sync to Pipfile.lock)"
    # Use Pipfile.lock when present; avoids drift.
    pipenv install

    echo "[${name}] Step 2: Generate deterministic requirements snapshot -> ${req_file}"
    # Prefer 'pipenv requirements' if available; fallback to pip freeze.
    if pipenv --help 2>/dev/null | grep -q "requirements"; then
      pipenv requirements > "${req_file}"
    else
      pipenv run python -m pip freeze > "${req_file}"
    fi

    echo "[${name}] Requirements snapshot (first 25 lines):"
    head -n 25 "${req_file}" || true
    echo ""

    echo "[${name}] Step 3: Install deps into build dir via pip --target"
    # This puts all dependencies directly into the lambda root (build_subdir),
    # which is exactly what AWS Lambda expects for zip deployments.
    #
    # We use pip within the pipenv environment so it uses the same resolver/index config.
    pipenv run python -m pip install \
      --disable-pip-version-check \
      --no-input \
      --no-compile \
      -r "${req_file}" \
      -t "${build_subdir}"

    echo "[${name}] Step 4: Copy lambda source into build dir"
    cp -R "${src_dir}/." "${build_subdir}/"
  )

  echo "[${name}] Step 5: Optional cleanup (smaller ZIP, safe)"
  rm -rf "${build_subdir}/__pycache__" || true
  find "${build_subdir}" -name "*.pyc" -delete || true
  find "${build_subdir}" -name "*.dist-info" -maxdepth 2 -type d -print >/dev/null 2>&1 || true

  echo "[${name}] Step 6: Create ZIP -> ${zip_path}"
  rm -f "${zip_path}"
  (
    cd "${build_subdir}"
    zip -qr "${zip_path}" .
  )

  echo "[${name}] DONE"
  echo "[${name}] Artifact size:"
  ls -lh "${zip_path}" || true
  echo ""
}

build_lambda_from_pipenv "${QSINK_NAME}" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC_DIR}"

echo "============================================================"
echo " Build complete "
echo "============================================================"
echo "Artifacts:"
ls -lh "${ARTIFACT_DIR}" || true
echo ""
echo "Requirements snapshots:"
ls -lh "${BUILD_DIR}"/requirements_*.txt || true
echo ""




////////////////////////



#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# LocalStack READY init script (runs when LocalStack is ready)
#
# What it does:
#   - Loads /project/.env (mounted from repo root .env)
#   - Creates:
#       * S3 bucket for QSink
#       * SQS: QSink queue + Enrollment queue + Enrollment DLQ (redrive configured)
#       * SecretsManager secret for DB
#   - Deploys the QSink lambda from /artifacts/qsink-referrals-enrollment.zip
#   - Wires:
#       * S3 ObjectCreated -> QSink SQS queue
#       * QSink SQS queue -> Lambda (event source mapping)
#
# What it intentionally does NOT do:
#   - No pip installs
#   - No building ZIPs
#   - No DockerHub pulls
# =============================================================================

echo "============================================================"
echo "[bootstrap] Starting LocalStack enrollment initialization"
echo "============================================================"

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

ENV_FILE="/project/.env"
if [[ -f "${ENV_FILE}" ]]; then
  echo "[bootstrap] Loading env from ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "[bootstrap] WARN: ${ENV_FILE} not found. Using defaults."
fi

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"
ENROLLMENT_DLQ_NAME="${ENROLLMENT_DLQ_NAME:-${ENROLLMENT_QUEUE_NAME}-dlq}"
SECRET_NAME="${SECRET_ARN:-enrollment-db-local}"

ARTIFACT_ZIP="/artifacts/qsink-referrals-enrollment.zip"
FUNCTION_NAME="qsink-forwarder-lambda"
HANDLER_PATH="handler.lambda_handler"
RUNTIME="python3.12"

echo ""
echo "[bootstrap] Effective configuration:"
echo "  AWS_REGION            = ${AWS_REGION}"
echo "  QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "  QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "  ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "  ENROLLMENT_DLQ_NAME   = ${ENROLLMENT_DLQ_NAME}"
echo "  SECRET_NAME           = ${SECRET_NAME}"
echo "  ARTIFACT_ZIP          = ${ARTIFACT_ZIP}"
echo "  FUNCTION_NAME         = ${FUNCTION_NAME}"
echo "  HANDLER               = ${HANDLER_PATH}"
echo ""

if [[ ! -f "${ARTIFACT_ZIP}" ]]; then
  echo "[bootstrap] ERROR: Missing lambda ZIP at ${ARTIFACT_ZIP}"
  echo "[bootstrap] Fix: run on host: ./localstack/build_lambdas.sh"
  exit 1
fi

echo "[bootstrap] 1) Create S3 bucket (idempotent): ${QSINK_BUCKET_NAME}"
awslocal s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || true

echo "[bootstrap] 2) Create DLQ (idempotent): ${ENROLLMENT_DLQ_NAME}"
awslocal sqs create-queue --queue-name "${ENROLLMENT_DLQ_NAME}" >/dev/null 2>&1 || true
ENROLLMENT_DLQ_URL="$(awslocal sqs get-queue-url --queue-name "${ENROLLMENT_DLQ_NAME}" --query QueueUrl --output text)"
ENROLLMENT_DLQ_ARN="$(awslocal sqs get-queue-attributes --queue-url "${ENROLLMENT_DLQ_URL}" --attribute-names QueueArn --query Attributes.QueueArn --output text)"

echo "[bootstrap] 3) Create Enrollment queue (idempotent): ${ENROLLMENT_QUEUE_NAME}"
awslocal sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || true
ENROLLMENT_QUEUE_URL="$(awslocal sqs get-queue-url --queue-name "${ENROLLMENT_QUEUE_NAME}" --query QueueUrl --output text)"

echo "[bootstrap] 4) Apply redrive policy to Enrollment queue -> DLQ"
REDRIVE_JSON="{\"deadLetterTargetArn\":\"${ENROLLMENT_DLQ_ARN}\",\"maxReceiveCount\":\"3\"}"
awslocal sqs set-queue-attributes \
  --queue-url "${ENROLLMENT_QUEUE_URL}" \
  --attributes RedrivePolicy="${REDRIVE_JSON}" >/dev/null 2>&1 || true

echo "[bootstrap] 5) Create QSink queue (idempotent): ${QSINK_QUEUE_NAME}"
awslocal sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || true
QSINK_QUEUE_URL="$(awslocal sqs get-queue-url --queue-name "${QSINK_QUEUE_NAME}" --query QueueUrl --output text)"
QSINK_QUEUE_ARN="$(awslocal sqs get-queue-attributes --queue-url "${QSINK_QUEUE_URL}" --attribute-names QueueArn --query Attributes.QueueArn --output text)"

echo "[bootstrap] 6) Create/Update SecretsManager secret: ${SECRET_NAME}"
if [[ -n "${DB_SECRET_JSON:-}" ]]; then
  SECRET_PAYLOAD="${DB_SECRET_JSON}"
else
  SECRET_PAYLOAD="{\"host\":\"${DB_HOST}\",\"port\":\"${DB_PORT}\",\"dbname\":\"${DB_NAME}\",\"username\":\"${DB_USER}\",\"password\":\"${DB_PASSWORD}\"}"
fi

if awslocal secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
  awslocal secretsmanager put-secret-value --secret-id "${SECRET_NAME}" --secret-string "${SECRET_PAYLOAD}" >/dev/null
else
  awslocal secretsmanager create-secret --name "${SECRET_NAME}" --secret-string "${SECRET_PAYLOAD}" >/dev/null
fi

echo "[bootstrap] 7) Ensure IAM role exists (lambda requires a role ARN)"
ROLE_NAME="localstack-lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
ASSUME_DOC="/tmp/assume-role.json"
cat > "${ASSUME_DOC}" <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
awslocal iam create-role --role-name "${ROLE_NAME}" --assume-role-policy-document "file://${ASSUME_DOC}" >/dev/null 2>&1 || true

echo "[bootstrap] 8) Deploy/update Lambda from ZIP"
# Lambda expects DESTINATION_SQS_QUEUE_URL
ENV_VARS="Variables={DESTINATION_SQS_QUEUE_URL=${ENROLLMENT_QUEUE_URL},LOG_LEVEL=${LOG_LEVEL:-DEBUG}}"

if awslocal lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  echo "[bootstrap] Lambda exists -> update code + config"
  awslocal lambda update-function-code --function-name "${FUNCTION_NAME}" --zip-file "fileb://${ARTIFACT_ZIP}" >/dev/null
  awslocal lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --runtime "${RUNTIME}" \
    --handler "${HANDLER_PATH}" \
    --role "${ROLE_ARN}" \
    --environment "${ENV_VARS}" >/dev/null
else
  echo "[bootstrap] Lambda missing -> create"
  awslocal lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --runtime "${RUNTIME}" \
    --handler "${HANDLER_PATH}" \
    --zip-file "fileb://${ARTIFACT_ZIP}" \
    --role "${ROLE_ARN}" \
    --environment "${ENV_VARS}" >/dev/null
fi

echo "[bootstrap] 9) Wire SQS (QSink queue) -> Lambda (event source mapping)"
MAPPING_UUID="$(awslocal lambda list-event-source-mappings \
  --function-name "${FUNCTION_NAME}" \
  --event-source-arn "${QSINK_QUEUE_ARN}" \
  --query 'EventSourceMappings[0].UUID' --output text 2>/dev/null || true)"

if [[ -z "${MAPPING_UUID}" || "${MAPPING_UUID}" == "None" ]]; then
  awslocal lambda create-event-source-mapping \
    --function-name "${FUNCTION_NAME}" \
    --event-source-arn "${QSINK_QUEUE_ARN}" \
    --batch-size 10 \
    --enabled >/dev/null
else
  echo "[bootstrap] Event source mapping already exists: ${MAPPING_UUID}"
fi

echo "[bootstrap] 10) Wire S3 -> QSink SQS (policy + bucket notification)"
SQS_POLICY="/tmp/qsink-sqs-policy.json"
cat > "${SQS_POLICY}" <<EOF
{
  "Version":"2012-10-17",
  "Statement":[
    {
      "Sid":"AllowS3SendMessage",
      "Effect":"Allow",
      "Principal":{"Service":"s3.amazonaws.com"},
      "Action":"sqs:SendMessage",
      "Resource":"${QSINK_QUEUE_ARN}",
      "Condition":{"ArnEquals":{"aws:SourceArn":"arn:aws:s3:::${QSINK_BUCKET_NAME}"}}
    }
  ]
}
EOF
awslocal sqs set-queue-attributes --queue-url "${QSINK_QUEUE_URL}" --attributes Policy="$(cat "${SQS_POLICY}")" >/dev/null 2>&1 || true

NOTIF_JSON="/tmp/s3-notification.json"
cat > "${NOTIF_JSON}" <<EOF
{
  "QueueConfigurations": [
    {
      "Id": "qsink-s3-put-to-sqs",
      "QueueArn": "${QSINK_QUEUE_ARN}",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
EOF
awslocal s3api put-bucket-notification-configuration \
  --bucket "${QSINK_BUCKET_NAME}" \
  --notification-configuration "file://${NOTIF_JSON}" >/dev/null 2>&1 || true

echo ""
echo "============================================================"
echo "[bootstrap] DONE. Summary:"
echo "  S3 bucket           : ${QSINK_BUCKET_NAME}"
echo "  QSink queue URL     : ${QSINK_QUEUE_URL}"
echo "  Enrollment queue URL: ${ENROLLMENT_QUEUE_URL}"
echo "  DLQ URL             : ${ENROLLMENT_DLQ_URL}"
echo "  Secret name         : ${SECRET_NAME}"
echo "  Lambda              : ${FUNCTION_NAME}"
echo "============================================================"
echo ""






////////////////////////////




services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment

    env_file:
      - ../.env

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"

    extra_hosts:
      - "host.docker.internal:host-gateway"

    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:4566/_localstack/health"]
      interval: 20s
      timeout: 5s
      retries: 30

    environment:
      ACTIVATE_PRO: ${ACTIVATE_PRO:-0}
      LOCALSTACK_AUTH_TOKEN: ${LOCALSTACK_AUTH_TOKEN}

      SERVICES: s3,sqs,secretsmanager,lambda,logs,iam,cloudwatch
      DEBUG: "1"

      AWS_DEFAULT_REGION: ${AWS_DEFAULT_REGION:-us-east-1}
      AWS_REGION: ${AWS_REGION:-us-east-1}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-localstack}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-localstack}

      # Proxy + CA pass-through (LocalStack may not need outbound access with this design)
      HTTP_PROXY: ${HTTP_PROXY:-}
      HTTPS_PROXY: ${HTTPS_PROXY:-}
      NO_PROXY: ${NO_PROXY:-}
      OUTBOUND_HTTP_PROXY: ${HTTP_PROXY:-}
      OUTBOUND_HTTPS_PROXY: ${HTTPS_PROXY:-}
      REQUESTS_CA_BUNDLE: ${REQUESTS_CA_BUNDLE:-}
      CURL_CA_BUNDLE: ${CURL_CA_BUNDLE:-}
      NODE_EXTRA_CA_CERTS: ${NODE_EXTRA_CA_CERTS:-}

      # Lambda runtime mapping to internal image (avoids DockerHub pulls)
      DOCKER_HOST: unix:///var/run/docker.sock
      LAMBDA_RUNTIME_IMAGE_MAPPING: '{"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}'
      LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT: "600000"
      LOCALSTACK_HOST: localstack
      LOCALSTACK_HOSTNAME: localstack

    volumes:
      - ..:/var/task

      # READY init script: 00- prefix = predictable execution order
      - ./00-enrollment-init.sh:/etc/localstack/init/ready.d/00-enrollment-init.sh:ro

      - /var/run/docker.sock:/var/run/docker.sock
      - ${HOME}/certs:/root/certs:ro

      # .env for bootstrap to read
      - ../.env:/project/.env:ro

      # Lambda ZIP artifacts built on host
      - ../.localstack/artifacts:/artifacts:ro

      # State
      - ../.localstack/volume:/var/lib/localstack

    restart: unless-stopped

  enrollment-writer:
    build:
      context: ..
      dockerfile: Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer

    env_file:
      - ../.env

    depends_on:
      localstack:
        condition: service_healthy

    # Bypass base-image entrypoint that requires /app/sm_secrets.yaml
    # (No code changes; we just run your module directly.)
    entrypoint: ["python", "-m", "enrollment_writer.app.main"]

    environment:
      AWS_ENDPOINT_URL: http://localstack:4566
      AWS_DEFAULT_REGION: ${AWS_DEFAULT_REGION:-us-east-1}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-localstack}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-localstack}

      SOURCE_SQS_QUEUE_URL: http://sqs.${AWS_DEFAULT_REGION:-us-east-1}.localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME:-sqsq2}
      SECRET_ARN: ${SECRET_ARN:-enrollment-db-local}

    restart: unless-stopped






////////////////////////////




#!/usr/bin/env bash
set -euo pipefail

# One command to:
#   1) Build lambda ZIP(s) locally
#   2) Start docker compose
# This avoids extra manual steps and avoids building inside LocalStack.

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

echo "[run] Building lambda ZIP(s) locally..."
./build_lambdas.sh

echo "[run] Starting docker compose..."
docker compose up --build




////////////////////////



chmod +x localstack/run.sh localstack/build_lambdas.sh localstack/00-enrollment-init.sh



./localstack/run.sh



docker logs -f localstack-enrollment
docker logs -f enrollment-writer


