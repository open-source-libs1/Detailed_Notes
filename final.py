#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

# -----------------------------
# Paths
# -----------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log "SCRIPT_DIR=${SCRIPT_DIR}"
log "REPO_ROOT=${REPO_ROOT}"

# Always run behave from repo root so it finds: tests/component/features/steps
cd "${REPO_ROOT}"

# -----------------------------
# Load .env (if present)
# -----------------------------
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  log "Loaded ${ENV_FILE}"
  # shellcheck disable=SC1090
  set -a && source "${ENV_FILE}" && set +a
else
  log "NOTE: ${ENV_FILE} not found; continuing with current env."
fi

# -----------------------------
# Host-vs-container endpoint
# -----------------------------
# IMPORTANT:
# - When you run component tests on the HOST (pipenv), "localstack" hostname usually does NOT resolve.
# - Use localhost for the endpoint and queue URLs.
ENDPOINT_HOST="${ENDPOINT_HOST:-localhost}"
ENDPOINT_PORT="${ENDPOINT_PORT:-4566}"
ENDPOINT="http://${ENDPOINT_HOST}:${ENDPOINT_PORT}"

log "Using endpoint: ${ENDPOINT}"
log "Using region: ${AWS_DEFAULT_REGION:-us-east-1}"

# Provide common endpoint envs in case your code reads them (environment_global, etc.)
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_REGION="${AWS_DEFAULT_REGION}"
export LOCALSTACK_ENDPOINT="${ENDPOINT}"
export AWS_ENDPOINT_URL="${ENDPOINT}"
export AWS_ENDPOINT_URL_SQS="${ENDPOINT}"
export AWS_ENDPOINT_URL_S3="${ENDPOINT}"
export AWS_ENDPOINT_URL_SECRETSMANAGER="${ENDPOINT}"

# Ensure ENVIRONMENT exists (your behave env.py reads it)
export ENVIRONMENT="${ENVIRONMENT:-local}"
log "ENVIRONMENT=${ENVIRONMENT}"

# -----------------------------
# DB config (host-run tests)
# -----------------------------
# Your .env may have DB_HOST=host.docker.internal (good for containers).
# For host-run tests, keep localhost.
export DB_NAME="${DB_NAME:-referrals_db}"
export DB_USER="${DB_USER:-postgres}"
export DB_PASSWORD="${DB_PASSWORD:-postgres}"
export DB_PORT="${DB_PORT:-29464}"

if [[ "${DB_HOST:-}" == "host.docker.internal" ]]; then
  log "NOTE: DB_HOST=host.docker.internal is for containers. Overriding to localhost for host-run tests."
  export DB_HOST="localhost"
else
  export DB_HOST="${DB_HOST:-localhost}"
fi

log "DB effective config: host=${DB_HOST} port=${DB_PORT} db=${DB_NAME} user=${DB_USER}"

# -----------------------------
# CA bundle (set INSIDE script)
# -----------------------------
# Your pip/pipenv run on HOST needs a HOST-valid CA path (not /root/...).
HOST_CA_BUNDLE="${HOST_CA_BUNDLE:-${HOME}/certs/C1G2RootCA.crt}"
if [[ -f "${HOST_CA_BUNDLE}" ]]; then
  export REQUESTS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export AWS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export CURL_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export SSL_CERT_FILE="${HOST_CA_BUNDLE}"
  log "Using HOST CA bundle: ${HOST_CA_BUNDLE}"
else
  log "WARNING: HOST_CA_BUNDLE not found at: ${HOST_CA_BUNDLE}"
  log "WARNING: If pipenv install hits TLS issues, set HOST_CA_BUNDLE in localstack/.env to a valid host path."
fi

# -----------------------------
# Health check (bounded; won’t hang forever)
# -----------------------------
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-30}"
SLEEP_SECONDS=2

log "Waiting for LocalStack bootstrap to be healthy (max ${MAX_WAIT_SECONDS}s)..."
start_ts="$(date +%s)"
while true; do
  # Avoid proxy interference on health checks
  if curl -fsS --max-time 2 --noproxy "*" "${ENDPOINT}/_localstack/health" >/dev/null 2>&1 \
    || curl -fsS --max-time 2 --noproxy "*" "${ENDPOINT}/health" >/dev/null 2>&1; then
    log "LocalStack is healthy."
    break
  fi

  now_ts="$(date +%s)"
  if (( now_ts - start_ts >= MAX_WAIT_SECONDS )); then
    log "WARNING: Health check timeout after ${MAX_WAIT_SECONDS}s. Continuing anyway."
    break
  fi
  sleep "${SLEEP_SECONDS}"
done

# -----------------------------
# Resolve SQS queue URL for sqsq2 (sanitize escapes)
# -----------------------------
QUEUE_NAME="${QUEUE_NAME:-sqsq2}"
log "Resolving QueueUrl for ${QUEUE_NAME}..."

# Use --output text to avoid JSON escaping (http:\/\/...)
RAW_QUEUE_URL="$(
  aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
    --queue-name "${QUEUE_NAME}" \
    --query 'QueueUrl' \
    --output text 2>/dev/null || true
)"

if [[ -z "${RAW_QUEUE_URL}" || "${RAW_QUEUE_URL}" == "None" ]]; then
  log "ERROR: Could not resolve QueueUrl for ${QUEUE_NAME}."
  log "TIP: Make sure bootstrap created the queue. Try: aws --endpoint-url='${ENDPOINT}' sqs list-queues"
  exit 1
fi

# Extra safety: strip quotes and unescape any accidental http:\/\/
SANITIZED_QUEUE_URL="$(echo "${RAW_QUEUE_URL}" | tr -d '"' | sed 's#\\/#/#g')"
export SQS_QUEUE_URL="${SANITIZED_QUEUE_URL}"
log "SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# Print the exact env vars your behave environment.py expects
log "Env summary:"
log "  ENVIRONMENT=${ENVIRONMENT}"
log "  AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}"
log "  AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL}"
log "  SQS_QUEUE_URL=${SQS_QUEUE_URL}"
log "  DB_NAME=${DB_NAME}"
log "  DB_HOST=${DB_HOST}"
log "  DB_USER=${DB_USER}"
log "  DB_PASSWORD=${DB_PASSWORD}"
log "  DB_PORT=${DB_PORT}"

# -----------------------------
# Install deps + run behave
# -----------------------------
log "Installing python deps via pipenv (host)..."
# Prefer sync to exactly match Pipfile.lock; fall back to install if needed.
if command -v pipenv >/dev/null 2>&1; then
  pipenv sync --dev || pipenv install --dev
else
  log "ERROR: pipenv not found on PATH."
  exit 1
fi

mkdir -p "${REPO_ROOT}/reports"

log "Running behave..."
# Use python -m behave to avoid “behave could not be found” edge cases.
pipenv run python -m behave tests/component/features \
  --format=json.pretty \
  --outfile="${REPO_ROOT}/reports/cucumber.json"

log "Done."
