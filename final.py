#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

log "SCRIPT_DIR=${SCRIPT_DIR}"
log "REPO_ROOT=${REPO_ROOT}"

# Load localstack/.env if present (expects KEY=VALUE lines)
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  log "Loaded ${ENV_FILE}"
else
  log "WARN: ${ENV_FILE} not found. Continuing with defaults."
fi

# -----------------------------
# 1) Force host-safe LocalStack endpoint
# -----------------------------
ENDPOINT="${ENDPOINT:-http://localhost:4566}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-${AWS_REGION:-us-east-1}}"

export ENDPOINT
export AWS_DEFAULT_REGION
export AWS_REGION="${AWS_DEFAULT_REGION}"

# IMPORTANT:
# Your logs showed: "Found endpoint for sqs via environment_global."
# That means something is reading env vars to pick service endpoints.
# For host-run tests we must NOT use 'http://localstack:4566' (that is for containers).
export AWS_ENDPOINT_URL="${ENDPOINT}"
export AWS_ENDPOINT_URL_SQS="${ENDPOINT}"
export AWS_ENDPOINT_URL_SECRETSMANAGER="${ENDPOINT}"
export AWS_ENDPOINT_URL_S3="${ENDPOINT}"

log "Using endpoint: ${ENDPOINT}"
log "Using region:   ${AWS_DEFAULT_REGION}"

# -----------------------------
# 2) Required test env vars (fixes KeyError: 'ENVIRONMENT')
# -----------------------------
export ENVIRONMENT="${ENVIRONMENT:-local}"

# -----------------------------
# 3) DB config (host-run tests should use localhost)
# -----------------------------
export DB_NAME="${DB_NAME:-referrals_db}"
export DB_USER="${DB_USER:-postgres}"
export DB_PASSWORD="${DB_PASSWORD:-postgres}"
export DB_PORT="${DB_PORT:-29464}"
export DB_HOST="${DB_HOST:-localhost}"

# If your .env is tuned for containers, it may set DB_HOST=host.docker.internal.
# That is fine for containers, but host-run tests should use localhost.
if [[ "${DB_HOST}" == "host.docker.internal" ]]; then
  log "NOTE: DB_HOST=host.docker.internal is for containers. Overriding to localhost for host-run tests."
  export DB_HOST="localhost"
fi

log "DB effective config: host=${DB_HOST} port=${DB_PORT} db=${DB_NAME} user=${DB_USER}"

# -----------------------------
# 4) Resolve the LocalStack SQS queue URL we want tests to use
#    (component tests should point to sqsq2 in your setup)
# -----------------------------
QUEUE_NAME="${QUEUE_NAME:-sqsq2}"
log "Resolving QueueUrl for ${QUEUE_NAME}..."

SQS_QUEUE_URL="$(
  aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
    --queue-name "${QUEUE_NAME}" \
    --query 'QueueUrl' \
    --output text 2>/dev/null || true
)"

if [[ -z "${SQS_QUEUE_URL}" || "${SQS_QUEUE_URL}" == "None" ]]; then
  log "ERROR: Queue '${QUEUE_NAME}' not found in LocalStack yet."
  log "       Start the stack first (./run.sh) and wait for bootstrap to complete, then re-run:"
  log "       ./run.sh test component"
  exit 1
fi

export SQS_QUEUE_URL
log "SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# -----------------------------
# 5) Corporate CA bundle for host pipenv/pip (so you don't export it manually)
# -----------------------------
HOST_CA_BUNDLE="${HOST_CA_BUNDLE:-${HOME}/certs/C1G2RootCA.crt}"
if [[ -f "${HOST_CA_BUNDLE}" ]]; then
  export CURL_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export REQUESTS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export SSL_CERT_FILE="${HOST_CA_BUNDLE}"
  export PIP_CERT="${HOST_CA_BUNDLE}"
  log "Using HOST CA bundle: ${HOST_CA_BUNDLE}"
else
  log "WARN: HOST_CA_BUNDLE not found at: ${HOST_CA_BUNDLE}"
  log "      If pipenv installs from Artifactory fail, set HOST_CA_BUNDLE to the correct file and retry."
fi

# Keep common local targets out of proxy
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,localstack,.local}"
log "NO_PROXY=${NO_PROXY}"

# -----------------------------
# 6) Run component tests
# -----------------------------
cd "${REPO_ROOT}"
mkdir -p reports

log "Installing python deps via pipenv (host)..."
pipenv install --dev

log "Running behave..."
pipenv run behave tests/component/features \
  --format=json.pretty \
  --outfile=./reports/cucumber.json
