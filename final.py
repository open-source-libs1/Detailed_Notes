#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log "SCRIPT_DIR=${SCRIPT_DIR}"
log "REPO_ROOT=${REPO_ROOT}"

# -------- Load env file (prefer .env.localstack, fallback .env) --------
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env.localstack}"
[[ -f "${ENV_FILE}" ]] || ENV_FILE="${SCRIPT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  log "Loaded ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  log "WARN: No env file found at ${SCRIPT_DIR}/.env.localstack or ${SCRIPT_DIR}/.env"
fi

# -------- CA bundle (no manual export needed) --------
# Prefer explicit HOST_CA_BUNDLE if already provided; else default to your shown path.
if [[ -z "${HOST_CA_BUNDLE:-}" ]]; then
  if [[ -f "${HOME}/certs/C1G2RootCA.crt" ]]; then
    export HOST_CA_BUNDLE="${HOME}/certs/C1G2RootCA.crt"
  fi
fi

if [[ -n "${HOST_CA_BUNDLE:-}" ]]; then
  export AWS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export REQUESTS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export CURL_CA_BUNDLE="${HOST_CA_BUNDLE}"
  log "Using HOST CA bundle: ${HOST_CA_BUNDLE}"
else
  log "WARN: HOST_CA_BUNDLE not set; continuing"
fi

# -------- Required defaults for LocalStack --------
export ENVIRONMENT="${ENVIRONMENT:-local}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"

# Host-run tests should normally hit localhost:4566.
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"
export AWS_ENDPOINT_URL_SQS="${AWS_ENDPOINT_URL_SQS:-${AWS_ENDPOINT_URL}}"

log "Using endpoint: ${AWS_ENDPOINT_URL}"
log "Using region:   ${AWS_DEFAULT_REGION}"
log "ENVIRONMENT=${ENVIRONMENT}"

# If .env is container-oriented, force host DB for host-run tests
if [[ "${DB_HOST:-}" == "host.docker.internal" ]]; then
  log "NOTE: DB_HOST=host.docker.internal is for containers. Overriding to localhost for host-run tests."
  export DB_HOST="localhost"
fi

log "DB effective config: host=${DB_HOST:-} port=${DB_PORT:-} db=${DB_NAME:-} user=${DB_USER:-}"

# -------- LocalStack health check (bounded) --------
if [[ "${SKIP_LOCALSTACK_HEALTH:-0}" == "1" ]]; then
  log "Skipping LocalStack health check (SKIP_LOCALSTACK_HEALTH=1)"
else
  timeout_s="${LOCALSTACK_HEALTH_TIMEOUT:-30}"
  log "Waiting for LocalStack bootstrap to be healthy (max ${timeout_s}s)..."
  start=$SECONDS
  while true; do
    if curl -fsS "${AWS_ENDPOINT_URL}/_localstack/health" >/dev/null 2>&1; then
      log "LocalStack is healthy."
      break
    fi
    if (( SECONDS - start >= timeout_s )); then
      log "WARN: LocalStack health endpoint not ready after ${timeout_s}s; continuing anyway."
      break
    fi
    sleep 2
  done
fi

# -------- Resolve QueueUrl (NO escaped slashes) --------
QUEUE_NAME="${QUEUE_NAME:-${SQS_QUEUE_NAME:-sqsq2}}"
log "Resolving QueueUrl for ${QUEUE_NAME}..."

SQS_QUEUE_URL=""
if command -v awslocal >/dev/null 2>&1; then
  # --output text avoids the http:\/\/ escaping problem
  SQS_QUEUE_URL="$(awslocal --endpoint-url "${AWS_ENDPOINT_URL_SQS}" \
    sqs get-queue-url \
    --queue-name "${QUEUE_NAME}" \
    --query 'QueueUrl' \
    --output text 2>/dev/null || true)"
fi

# Optional hardcode override if you REALLY want exactly what’s in your screenshot
# export SQS_QUEUE_URL_OVERRIDE="http://localstack:4566/queue/us-east-1/000000000000/sqsq2"
if [[ -z "${SQS_QUEUE_URL}" || "${SQS_QUEUE_URL}" == "None" ]]; then
  SQS_QUEUE_URL="${SQS_QUEUE_URL_OVERRIDE:-}"
fi

if [[ -z "${SQS_QUEUE_URL}" ]]; then
  log "ERROR: Could not resolve SQS_QUEUE_URL for ${QUEUE_NAME}."
  log "       Ensure the queue exists: awslocal --endpoint-url ${AWS_ENDPOINT_URL_SQS} sqs create-queue --queue-name ${QUEUE_NAME}"
  exit 1
fi

export SQS_QUEUE_URL
log "SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# -------- Print env vars (as requested) --------
log "Env summary:"
for k in ENVIRONMENT AWS_DEFAULT_REGION AWS_ENDPOINT_URL AWS_ENDPOINT_URL_SQS SQS_QUEUE_URL \
         DB_NAME DB_HOST DB_USER DB_PASSWORD DB_PORT HOST_CA_BUNDLE AWS_CA_BUNDLE REQUESTS_CA_BUNDLE; do
  log "  ${k}=${!k-}"
done

# -------- Run tests from repo root (fixes steps-dir issue) --------
cd "${REPO_ROOT}"

log "Installing python deps via pipenv (host)..."
pipenv sync --dev

log "Running behave..."
mkdir -p "${REPO_ROOT}/reports"
pipenv run behave tests/component/features --format=json.pretty --outfile="${REPO_ROOT}/reports/cucumber.json"
