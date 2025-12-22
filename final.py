#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log "SCRIPT_DIR=${SCRIPT_DIR}"
log "REPO_ROOT=${REPO_ROOT}"

# ---- Load env (prefer .env.localstack) ----
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env.localstack}"
[[ -f "${ENV_FILE}" ]] || ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  log "Loaded ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  log "ERROR: env file not found (${SCRIPT_DIR}/.env.localstack or ${SCRIPT_DIR}/.env)"
  exit 1
fi

# ---- CA bundle (no manual export) ----
if [[ -z "${HOST_CA_BUNDLE:-}" && -f "${HOME}/certs/C1G2RootCA.crt" ]]; then
  export HOST_CA_BUNDLE="${HOME}/certs/C1G2RootCA.crt"
fi
if [[ -n "${HOST_CA_BUNDLE:-}" ]]; then
  export AWS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export REQUESTS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export CURL_CA_BUNDLE="${HOST_CA_BUNDLE}"
  log "Using HOST CA bundle: ${HOST_CA_BUNDLE}"
fi

# ---- Defaults ----
export ENVIRONMENT="${ENVIRONMENT:-local}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"

# Endpoint from env; for host-run tests normalize localstack->localhost
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"
if [[ "${AWS_ENDPOINT_URL}" == *"localstack:4566"* ]]; then
  log "NOTE: Host-run detected; normalizing AWS_ENDPOINT_URL localstack->localhost"
  AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL/localstack:4566/localhost:4566}"
  export AWS_ENDPOINT_URL
fi
export AWS_ENDPOINT_URL_SQS="${AWS_ENDPOINT_URL_SQS:-$AWS_ENDPOINT_URL}"
if [[ "${AWS_ENDPOINT_URL_SQS}" == *"localstack:4566"* ]]; then
  AWS_ENDPOINT_URL_SQS="${AWS_ENDPOINT_URL_SQS/localstack:4566/localhost:4566}"
  export AWS_ENDPOINT_URL_SQS
fi

log "Using endpoint: ${AWS_ENDPOINT_URL}"
log "Using region:   ${AWS_DEFAULT_REGION}"
log "ENVIRONMENT=${ENVIRONMENT}"

# DB host normalization (your existing logic)
if [[ "${DB_HOST:-}" == "host.docker.internal" ]]; then
  log "NOTE: DB_HOST=host.docker.internal is for containers. Overriding to localhost for host-run tests."
  export DB_HOST="localhost"
fi
log "DB effective config: host=${DB_HOST:-} port=${DB_PORT:-} db=${DB_NAME:-} user=${DB_USER:-}"

# ---- Print queues (requested) ----
if command -v awslocal >/dev/null 2>&1; then
  log "Listing queues via awslocal (endpoint=${AWS_ENDPOINT_URL_SQS})..."
  awslocal --endpoint-url "${AWS_ENDPOINT_URL_SQS}" sqs list-queues || true
else
  log "WARN: awslocal not found; cannot list queues."
fi

# ---- Use existing queue URL (no create-queue, no health checks) ----
# If your env already has SQS_QUEUE_URL, we keep it but normalize host-run.
if [[ -n "${SQS_QUEUE_URL:-}" && "${SQS_QUEUE_URL}" == *"localstack:4566"* ]]; then
  log "NOTE: Host-run detected; normalizing SQS_QUEUE_URL localstack->localhost"
  export SQS_QUEUE_URL="${SQS_QUEUE_URL/localstack:4566/localhost:4566}"
fi

QUEUE_NAME="${QUEUE_NAME:-${SQS_QUEUE_NAME:-sqsq2}}"
if [[ -z "${SQS_QUEUE_URL:-}" ]]; then
  log "Resolving QueueUrl for ${QUEUE_NAME}..."
  SQS_QUEUE_URL="$(awslocal --endpoint-url "${AWS_ENDPOINT_URL_SQS}" \
    sqs get-queue-url \
    --queue-name "${QUEUE_NAME}" \
    --query 'QueueUrl' \
    --output text 2>/dev/null || true)"
  if [[ -z "${SQS_QUEUE_URL}" || "${SQS_QUEUE_URL}" == "None" ]]; then
    log "ERROR: Could not resolve SQS_QUEUE_URL for ${QUEUE_NAME} at ${AWS_ENDPOINT_URL_SQS}"
    log "       (Most common cause: endpoint hostname mismatch; host should use localhost)"
    exit 1
  fi
  export SQS_QUEUE_URL
fi

log "SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# ---- Print env summary (requested) ----
log "Env summary:"
for k in ENVIRONMENT AWS_DEFAULT_REGION AWS_ENDPOINT_URL AWS_ENDPOINT_URL_SQS SQS_QUEUE_URL \
         DB_NAME DB_HOST DB_USER DB_PASSWORD DB_PORT HOST_CA_BUNDLE AWS_CA_BUNDLE REQUESTS_CA_BUNDLE; do
  log "  ${k}=${!k-}"
done

# ---- Run behave from repo root (fixes steps-dir issue) ----
cd "${REPO_ROOT}"
log "Installing python deps via pipenv (host)..."
pipenv sync --dev

log "Running behave..."
mkdir -p "${REPO_ROOT}/reports"
pipenv run behave tests/component/features --format=json.pretty --outfile="${REPO_ROOT}/reports/cucumber.json"
