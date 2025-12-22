# LocalStack Pro
ACTIVATE_PRO=0
LOCALSTACK_AUTH_TOKEN=ls-REPLACE_ME

# AWS / region
AWS_DEFAULT_REGION=us-east-1
AWS_REGION=us-east-1

# Dummy AWS creds for LocalStack
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack

# App toggles
APP_ENV=local
LOG_LEVEL=INFO
COF_SM_ENABLED=true

# Local resource names (must match bootstrap)
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

# Secret name the app uses (passed as SECRET_ARN into enrollment-writer)
SECRET_ARN=enrollment-db-local

# DB connection details (your local/DEV Postgres)
DB_HOST=host.docker.internal
DB_PORT=29464
DB_NAME=referrals_db
DB_USER=postgres
DB_PASSWORD=postgres

# Optional: explicit secret payload (Python-literal dict string is safest for ast.literal_eval)
# If you set this, bootstrap uses it as-is.
DB_SECRET_JSON={'host':'host.docker.internal','port':29464,'dbname':'referrals_db','username':'postgres','password':'postgres'}

# Corporate CA bundles (mounted into containers at /root/certs)
REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt

# Corporate proxy (if needed)
HTTP_PROXY=http://crtproxy.kdc.capitalone.com:8099
HTTPS_PROXY=http://crtproxy.kdc.capitalone.com:8099
NO_PROXY=127.0.0.1,localstack,localhost,.local,.internal,169.254.169.254,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com
http_proxy=http://crtproxy.kdc.capitalone.com:8099
https_proxy=http://crtproxy.kdc.capitalone.com:8099
no_proxy=127.0.0.1,localstack,localhost,.local,.internal,169.254.169.254,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com




////////////////////////////////////////////



services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment

    env_file:
      - ./.env

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"
      - "127.0.0.1:443:443"

    extra_hosts:
      - "host.docker.internal:host-gateway"

    environment:
      # LocalStack services needed
      SERVICES: "iam,lambda,logs,secretsmanager,s3,sqs,cloudwatch"

      # Pro activation
      ACTIVATE_PRO: "${ACTIVATE_PRO:-0}"
      LOCALSTACK_AUTH_TOKEN: "${LOCALSTACK_AUTH_TOKEN}"

      # Keep SQS URLs path-style (avoids sqs.<region>.<host> DNS issues in Docker)
      SQS_ENDPOINT_STRATEGY: "path"

      # Regions / creds
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"
      AWS_REGION: "${AWS_REGION:-us-east-1}"
      AWS_ACCESS_KEY_ID: "${AWS_ACCESS_KEY_ID:-localstack}"
      AWS_SECRET_ACCESS_KEY: "${AWS_SECRET_ACCESS_KEY:-localstack}"

      # Proxy/CA (if required)
      HTTP_PROXY: "${HTTP_PROXY}"
      HTTPS_PROXY: "${HTTPS_PROXY}"
      NO_PROXY: "${NO_PROXY}"
      OUTBOUND_HTTP_PROXY: "${HTTP_PROXY}"
      OUTBOUND_HTTPS_PROXY: "${HTTPS_PROXY}"
      REQUESTS_CA_BUNDLE: "${REQUESTS_CA_BUNDLE}"
      CURL_CA_BUNDLE: "${CURL_CA_BUNDLE}"
      NODE_EXTRA_CA_CERTS: "${NODE_EXTRA_CA_CERTS}"

      # Lambda docker execution (avoid DockerHub pulls by mapping runtime)
      DOCKER_HOST: "unix:///var/run/docker.sock"
      LAMBDA_RUNTIME_IMAGE_MAPPING: '{"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}'
      LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT: "600000"

    volumes:
      # Repo root (optional, but consistent with other team style)
      - ..:/var/task

      # LocalStack "ready" init hook (00- prefix = runs first)
      - ./00-enrollment-init.sh:/etc/localstack/init/ready.d/00-enrollment-init.sh:ro

      # Docker socket so LocalStack can run lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # Corporate root CA bundle mounted into /root/certs
      - ${HOME}/certs:/root/certs:ro

      # Persist LocalStack state
      - ./.localstack/volume:/var/lib/localstack

      # .env visible inside LocalStack init script
      - ./.env:/project/.env:ro

      # Lambda ZIP artifacts built on host
      - ./.localstack/artifacts:/artifacts:ro

    # IMPORTANT: healthcheck waits for YOUR secret, not just /health
    healthcheck:
      test:
        - "CMD-SHELL"
        - "awslocal secretsmanager describe-secret --secret-id \"$${SECRET_ARN:-enrollment-db-local}\" >/dev/null 2>&1"
      interval: 3s
      timeout: 3s
      retries: 120
      start_period: 10s

    restart: unless-stopped

  enrollment-writer:
    build:
      context: ..
      dockerfile: Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer

    env_file:
      - ./.env

    depends_on:
      localstack:
        condition: service_healthy

    environment:
      # App settings
      APP_ENV: "${APP_ENV:-local}"
      LOG_LEVEL: "${LOG_LEVEL:-INFO}"

      # DB vars (also stored in secret)
      DB_HOST: "${DB_HOST}"
      DB_PORT: "${DB_PORT}"
      DB_NAME: "${DB_NAME}"
      DB_USER: "${DB_USER}"
      DB_PASSWORD: "${DB_PASSWORD}"

      # Secret name enrollment-writer reads
      SECRET_ARN: "${SECRET_ARN:-enrollment-db-local}"

      # Point AWS SDK usage to LocalStack (your code/util already uses this)
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"
      AWS_REGION: "${AWS_REGION:-us-east-1}"
      AWS_ENDPOINT_URL: "http://localstack:4566"
      AWS_ACCESS_KEY_ID: "${AWS_ACCESS_KEY_ID:-localstack}"
      AWS_SECRET_ACCESS_KEY: "${AWS_SECRET_ACCESS_KEY:-localstack}"

      # IMPORTANT: use path-style queue url (resolves in Docker)
      SOURCE_SQS_QUEUE_URL: "http://localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME:-sqsq2}"

    restart: unless-stopped
services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment

    env_file:
      - ./.env

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"
      - "127.0.0.1:443:443"

    extra_hosts:
      - "host.docker.internal:host-gateway"

    environment:
      # LocalStack services needed
      SERVICES: "iam,lambda,logs,secretsmanager,s3,sqs,cloudwatch"

      # Pro activation
      ACTIVATE_PRO: "${ACTIVATE_PRO:-0}"
      LOCALSTACK_AUTH_TOKEN: "${LOCALSTACK_AUTH_TOKEN}"

      # Keep SQS URLs path-style (avoids sqs.<region>.<host> DNS issues in Docker)
      SQS_ENDPOINT_STRATEGY: "path"

      # Regions / creds
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"
      AWS_REGION: "${AWS_REGION:-us-east-1}"
      AWS_ACCESS_KEY_ID: "${AWS_ACCESS_KEY_ID:-localstack}"
      AWS_SECRET_ACCESS_KEY: "${AWS_SECRET_ACCESS_KEY:-localstack}"

      # Proxy/CA (if required)
      HTTP_PROXY: "${HTTP_PROXY}"
      HTTPS_PROXY: "${HTTPS_PROXY}"
      NO_PROXY: "${NO_PROXY}"
      OUTBOUND_HTTP_PROXY: "${HTTP_PROXY}"
      OUTBOUND_HTTPS_PROXY: "${HTTPS_PROXY}"
      REQUESTS_CA_BUNDLE: "${REQUESTS_CA_BUNDLE}"
      CURL_CA_BUNDLE: "${CURL_CA_BUNDLE}"
      NODE_EXTRA_CA_CERTS: "${NODE_EXTRA_CA_CERTS}"

      # Lambda docker execution (avoid DockerHub pulls by mapping runtime)
      DOCKER_HOST: "unix:///var/run/docker.sock"
      LAMBDA_RUNTIME_IMAGE_MAPPING: '{"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}'
      LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT: "600000"

    volumes:
      # Repo root (optional, but consistent with other team style)
      - ..:/var/task

      # LocalStack "ready" init hook (00- prefix = runs first)
      - ./00-enrollment-init.sh:/etc/localstack/init/ready.d/00-enrollment-init.sh:ro

      # Docker socket so LocalStack can run lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # Corporate root CA bundle mounted into /root/certs
      - ${HOME}/certs:/root/certs:ro

      # Persist LocalStack state
      - ./.localstack/volume:/var/lib/localstack

      # .env visible inside LocalStack init script
      - ./.env:/project/.env:ro

      # Lambda ZIP artifacts built on host
      - ./.localstack/artifacts:/artifacts:ro

    # IMPORTANT: healthcheck waits for YOUR secret, not just /health
    healthcheck:
      test:
        - "CMD-SHELL"
        - "awslocal secretsmanager describe-secret --secret-id \"$${SECRET_ARN:-enrollment-db-local}\" >/dev/null 2>&1"
      interval: 3s
      timeout: 3s
      retries: 120
      start_period: 10s

    restart: unless-stopped

  enrollment-writer:
    build:
      context: ..
      dockerfile: Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer

    env_file:
      - ./.env

    depends_on:
      localstack:
        condition: service_healthy

    environment:
      # App settings
      APP_ENV: "${APP_ENV:-local}"
      LOG_LEVEL: "${LOG_LEVEL:-INFO}"

      # DB vars (also stored in secret)
      DB_HOST: "${DB_HOST}"
      DB_PORT: "${DB_PORT}"
      DB_NAME: "${DB_NAME}"
      DB_USER: "${DB_USER}"
      DB_PASSWORD: "${DB_PASSWORD}"

      # Secret name enrollment-writer reads
      SECRET_ARN: "${SECRET_ARN:-enrollment-db-local}"

      # Point AWS SDK usage to LocalStack (your code/util already uses this)
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"
      AWS_REGION: "${AWS_REGION:-us-east-1}"
      AWS_ENDPOINT_URL: "http://localstack:4566"
      AWS_ACCESS_KEY_ID: "${AWS_ACCESS_KEY_ID:-localstack}"
      AWS_SECRET_ACCESS_KEY: "${AWS_SECRET_ACCESS_KEY:-localstack}"

      # IMPORTANT: use path-style queue url (resolves in Docker)
      SOURCE_SQS_QUEUE_URL: "http://localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME:-sqsq2}"

    restart: unless-stopped




/////////////////////////////




#!/usr/bin/env bash
set -euo pipefail

log() { echo "[$(date -Iseconds)] [00-enrollment-init] $*"; }

log "Starting LocalStack enrollment bootstrap..."

# LocalStack images include awslocal. If not, fall back to aws + endpoint.
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
else
  AWSLOCAL="aws --endpoint-url=http://localhost:4566"
fi
log "Using AWS CLI as: ${AWSLOCAL}"

# Load env file mounted by docker-compose
ENV_FILE="/project/.env"
if [[ -f "${ENV_FILE}" ]]; then
  log "Loading environment from ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  log "WARN: ${ENV_FILE} not found. Using defaults where possible."
fi

AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
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

log "Effective configuration:"
log "  AWS_REGION=${AWS_REGION}"
log "  QSINK_BUCKET_NAME=${QSINK_BUCKET_NAME}"
log "  QSINK_QUEUE_NAME=${QSINK_QUEUE_NAME}"
log "  ENROLLMENT_QUEUE_NAME=${ENROLLMENT_QUEUE_NAME}"
log "  SECRET_NAME=${SECRET_NAME}"
log "  QSINK_ZIP=${QSINK_ZIP}"
log "  FUNCTION_NAME=${FUNCTION_NAME}"

# --- 1) Create bucket (idempotent) ---
log "Creating S3 bucket (idempotent): ${QSINK_BUCKET_NAME}"
${AWSLOCAL} s3api head-bucket --bucket "${QSINK_BUCKET_NAME}" >/dev/null 2>&1 \
  || ${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null

# --- 2) Create queues (idempotent) ---
log "Creating SQS queues (idempotent): ${QSINK_QUEUE_NAME}, ${ENROLLMENT_QUEUE_NAME}"
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null
${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null

# For event-source mapping we need the queue ARN
QSINK_QUEUE_URL="$(${AWSLOCAL} sqs get-queue-url --queue-name "${QSINK_QUEUE_NAME}" --query 'QueueUrl' --output text)"
QSINK_QUEUE_ARN="$(${AWSLOCAL} sqs get-queue-attributes --queue-url "${QSINK_QUEUE_URL}" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)"
log "QSINK_QUEUE_URL=${QSINK_QUEUE_URL}"
log "QSINK_QUEUE_ARN=${QSINK_QUEUE_ARN}"

# --- 3) Create/update Secrets Manager secret (THIS is what enrollment-writer needs) ---
# enrollment-writer uses ast.literal_eval, so store a Python-literal dict string.
if [[ -n "${DB_SECRET_JSON:-}" ]]; then
  DB_SECRET_VALUE="${DB_SECRET_JSON}"
else
  DB_SECRET_VALUE="{'host':'${DB_HOST}','port':${DB_PORT},'dbname':'${DB_NAME}','username':'${DB_USER}','password':'${DB_PASSWORD}'}"
fi

log "Ensuring Secrets Manager secret exists: ${SECRET_NAME}"
if ${AWSLOCAL} secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
  log "Secret exists -> updating secret value"
  ${AWSLOCAL} secretsmanager put-secret-value \
    --secret-id "${SECRET_NAME}" \
    --secret-string "${DB_SECRET_VALUE}" >/dev/null
else
  log "Secret missing -> creating secret"
  ${AWSLOCAL} secretsmanager create-secret \
    --name "${SECRET_NAME}" \
    --secret-string "${DB_SECRET_VALUE}" >/dev/null
fi
log "Secret ready: ${SECRET_NAME}"

# --- 4) Create a dummy IAM role for Lambda (LocalStack requires a role ARN) ---
ROLE_NAME="lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

cat >/tmp/assume-role.json <<'EOF'
{
  "Version":"2012-10-17",
  "Statement":[
    {
      "Effect":"Allow",
      "Principal":{"Service":"lambda.amazonaws.com"},
      "Action":"sts:AssumeRole"
    }
  ]
}
EOF

if ${AWSLOCAL} iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  log "IAM role exists: ${ROLE_NAME}"
else
  log "Creating IAM role: ${ROLE_NAME}"
  ${AWSLOCAL} iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document file:///tmp/assume-role.json >/dev/null
fi

# --- 5) Deploy QSink lambda if ZIP exists ---
if [[ -f "${QSINK_ZIP}" ]]; then
  log "Lambda ZIP found -> deploying: ${QSINK_ZIP}"

  # Queue URL that resolves inside Docker network:
  DESTINATION_SQS_QUEUE_URL="http://localstack:4566/${ACCOUNT_ID}/${ENROLLMENT_QUEUE_NAME}"

  # Build env json for Lambda
  # Note: keep minimal; your lambda code reads DESTINATION_SQS_QUEUE_URL + LOG_LEVEL
  LAMBDA_ENV_JSON=$(cat <<EOF
{"Variables":{
  "LOG_LEVEL":"${LOG_LEVEL:-INFO}",
  "DESTINATION_SQS_QUEUE_URL":"${DESTINATION_SQS_QUEUE_URL}",
  "AWS_DEFAULT_REGION":"${AWS_REGION}",
  "AWS_REGION":"${AWS_REGION}",
  "AWS_ENDPOINT_URL":"http://localstack:4566"
}}
EOF
)

  if ${AWSLOCAL} lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
    log "Lambda exists -> updating code + configuration"
    ${AWSLOCAL} lambda update-function-code \
      --function-name "${FUNCTION_NAME}" \
      --zip-file "fileb://${QSINK_ZIP}" >/dev/null

    ${AWSLOCAL} lambda update-function-configuration \
      --function-name "${FUNCTION_NAME}" \
      --handler "${HANDLER_PATH}" \
      --runtime "${RUNTIME}" \
      --role "${ROLE_ARN}" \
      --environment "${LAMBDA_ENV_JSON}" >/dev/null
  else
    log "Lambda missing -> creating function"
    ${AWSLOCAL} lambda create-function \
      --function-name "${FUNCTION_NAME}" \
      --runtime "${RUNTIME}" \
      --handler "${HANDLER_PATH}" \
      --zip-file "fileb://${QSINK_ZIP}" \
      --role "${ROLE_ARN}" \
      --environment "${LAMBDA_ENV_JSON}" >/dev/null
  fi

  # Ensure SQS -> Lambda event source mapping exists (idempotent)
  log "Ensuring SQS event source mapping exists (QSINK_QUEUE -> Lambda)"
  EXISTING_MAPPING="$(${AWSLOCAL} lambda list-event-source-mappings \
    --function-name "${FUNCTION_NAME}" \
    --event-source-arn "${QSINK_QUEUE_ARN}" \
    --query 'EventSourceMappings[0].UUID' --output text 2>/dev/null || true)"

  if [[ -n "${EXISTING_MAPPING}" && "${EXISTING_MAPPING}" != "None" ]]; then
    log "Event source mapping already exists: ${EXISTING_MAPPING}"
  else
    ${AWSLOCAL} lambda create-event-source-mapping \
      --function-name "${FUNCTION_NAME}" \
      --event-source-arn "${QSINK_QUEUE_ARN}" \
      --batch-size 10 \
      --enabled >/dev/null
    log "Event source mapping created"
  fi

else
  log "WARN: Lambda ZIP not found at ${QSINK_ZIP}. Skipping lambda deploy."
  log "      Build it on host: ./build_lambdas.sh"
fi

# --- Summary / debug listing ---
log "Bootstrap complete. Resource summary:"
log "  Secret: ${SECRET_NAME}"
log "  Bucket: ${QSINK_BUCKET_NAME}"
log "  Queues:"
${AWSLOCAL} sqs list-queues || true
log "  Lambdas:"
${AWSLOCAL} lambda list-functions || true
log "DONE"




//////////////////////////////////




#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"

ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

# QSink Forwarder Lambda
QSINK_NAME="qsink-referrals-enrollment"
QSINK_PIPFILE_DIR="${REPO_ROOT}/qsink-referrals-enrollment"
QSINK_SRC_DIR="${REPO_ROOT}/qsink-referrals-enrollment/src"

# Enrollment Writer Lambda (zip not strictly needed if ECS-style; kept here only if you truly need it)
ENR_NAME="enrollment_writer"
ENR_PIPFILE_DIR="${REPO_ROOT}"
ENR_SRC_DIR="${REPO_ROOT}/enrollment_writer/app"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "=== BUILDING LAMBDA ZIPS ==="
echo "REPO_ROOT    = ${REPO_ROOT}"
echo "ARTIFACT_DIR = ${ARTIFACT_DIR}"
echo "BUILD_DIR    = ${BUILD_DIR}"
echo ""

build_lambda() {
  local name="$1"
  local pipfile_dir="$2"
  local src_dir="$3"

  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local zip_path="${ARTIFACT_DIR}/${name}.zip"

  echo ""
  echo "---- Building '${name}' ----"
  echo "[${name}] Pipfile dir: ${pipfile_dir}"
  echo "[${name}] Source dir : ${src_dir}"
  echo "[${name}] Build dir  : ${build_subdir}"
  echo "[${name}] Artifact   : ${zip_path}"

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  (
    cd "${pipfile_dir}"

    echo "[${name}] pipenv install (ensuring env is up to date)"
    pipenv install >/dev/null

    echo "[${name}] pip freeze -> ${req_file}"
    pipenv run pip freeze > "${req_file}"

    echo "[${name}] locating site-packages via pipenv -venv"
    VENV_DIR="$(pipenv -venv)"
    echo "[${name}] VENV_DIR=${VENV_DIR}"

    SITEPKG_CANDIDATE="$(ls -d "${VENV_DIR}"/lib/python*/site-packages 2>/dev/null | head -1 || true)"

    if [[ -n "${SITEPKG_CANDIDATE}" && -d "${SITEPKG_CANDIDATE}" ]]; then
      echo "[${name}] Using site-packages: ${SITEPKG_CANDIDATE}"
      echo "[${name}] Copying dependencies -> ${build_subdir}"
      cp -R "${SITEPKG_CANDIDATE}/." "${build_subdir}/"
    else
      echo "[${name}] WARN: site-packages not found. Falling back to pip install -r into build dir."
      echo "[${name}] This may download wheels; ensure proxy/PIP_INDEX_URL works if required."
      pipenv run python -m pip install -r "${req_file}" -t "${build_subdir}" >/dev/null
    fi
  )

  echo "[${name}] Copying lambda source -> ${build_subdir}"
  cp -R "${src_dir}/." "${build_subdir}/"

  echo "[${name}] Creating zip -> ${zip_path}"
  (
    cd "${build_subdir}"
    zip -r "${zip_path}" . >/dev/null
  )
  echo "[${name}] DONE"
}

# Build only what you actually need. If enrollment-writer is ECS-only, you can comment it out.
build_lambda "${QSINK_NAME}" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC_DIR}"
# build_lambda "${ENR_NAME}" "${ENR_PIPFILE_DIR}" "${ENR_SRC_DIR}"

echo ""
echo "=== BUILD COMPLETE ==="
ls -lh "${ARTIFACT_DIR}" || true
echo ""




////////////////////




#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

cmd="${1:-up}"

case "${cmd}" in
  build)
    ./build_lambdas.sh
    ;;
  up)
    ./build_lambdas.sh
    docker compose up --build
    ;;
  down)
    docker compose down -v
    ;;
  logs)
    docker compose logs -f --tail=200
    ;;
  *)
    echo "Usage: $0 {build|up|down|logs}"
    exit 1
    ;;
esac





//////////////////////



chmod +x localstack/*.sh
cd localstack
./run.sh up


