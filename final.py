#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

# --- Paths ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log "SCRIPT_DIR=${SCRIPT_DIR}"
log "REPO_ROOT=${REPO_ROOT}"

# --- LocalStack endpoint (host-run) ---
# IMPORTANT: component tests run on the HOST, so LocalStack must be reachable via localhost.
ENDPOINT="${ENDPOINT:-http://localhost:4566}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION}}"

# Some codepaths pick endpoints up from env; set both generic and SQS-specific just in case.
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-$ENDPOINT}"
export AWS_ENDPOINT_URL_SQS="${AWS_ENDPOINT_URL_SQS:-$ENDPOINT}"

log "Using endpoint: ${ENDPOINT}"
log "Using region:   ${AWS_DEFAULT_REGION}"

# --- Ensure ENVIRONMENT exists (tests expect it) ---
# Your behave environment.py uses os.environ['ENVIRONMENT'], so missing it hard-fails.
export ENVIRONMENT="${ENVIRONMENT:-local}"
log "ENVIRONMENT=${ENVIRONMENT}"

# --- CA bundle (fix pip/pipenv TLS + boto/requests when needed) ---
# If you already export HOST_CA_BUNDLE outside, we will respect it.
if [[ -z "${HOST_CA_BUNDLE:-}" ]]; then
  # Default convention you’ve been using
  if [[ -f "${HOME}/certs/C1G2RootCA.crt" ]]; then
    HOST_CA_BUNDLE="${HOME}/certs/C1G2RootCA.crt"
  fi
fi

if [[ -n "${HOST_CA_BUNDLE:-}" ]]; then
  if [[ -f "${HOST_CA_BUNDLE}" ]]; then
    log "Using HOST CA bundle: ${HOST_CA_BUNDLE}"
    export REQUESTS_CA_BUNDLE="${HOST_CA_BUNDLE}"
    export AWS_CA_BUNDLE="${HOST_CA_BUNDLE}"
    export CURL_CA_BUNDLE="${HOST_CA_BUNDLE}"
    export PIP_CERT="${HOST_CA_BUNDLE}"
    export SSL_CERT_FILE="${HOST_CA_BUNDLE}"
  else
    log "WARNING: HOST_CA_BUNDLE is set but file not found: ${HOST_CA_BUNDLE}"
  fi
else
  log "NOTE: HOST_CA_BUNDLE not set; continuing without explicit CA bundle."
fi

# --- DB defaults for HOST-run tests ---
# Your DB is exposed to the host via a mapped port, so host=localhost is correct.
export DB_NAME="${DB_NAME:-referrals_db}"
export DB_USER="${DB_USER:-postgres}"
export DB_PASSWORD="${DB_PASSWORD:-postgres}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-29464}"

log "DB effective config: host=${DB_HOST} port=${DB_PORT} db=${DB_NAME} user=${DB_USER}"

# --- Wait for LocalStack to be healthy ---
log "Waiting for LocalStack bootstrap to be healthy..."
for _ in {1..90}; do
  if curl -fsS "${ENDPOINT}/_localstack/health" >/dev/null 2>&1; then
    log "LocalStack is healthy."
    break
  fi
  sleep 2
done

# --- Resolve QueueUrl (component tests use SQS_QUEUE_URL) ---
QUEUE_NAME="${QUEUE_NAME:-sqsq2}"
log "Resolving QueueUrl for ${QUEUE_NAME}..."

QUEUE_URL="$(
  aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
    --queue-name "${QUEUE_NAME}" \
    --query 'QueueUrl' \
    --output text 2>/dev/null || true
)"

if [[ -z "${QUEUE_URL}" || "${QUEUE_URL}" == "None" ]]; then
  log "ERROR: Could not resolve QueueUrl for ${QUEUE_NAME}."
  log "Try: aws --endpoint-url=${ENDPOINT} sqs list-queues"
  exit 1
fi

# IMPORTANT:
# Sometimes LocalStack returns QueueUrl with host "localstack:4566" (container hostname),
# which FAILS for host-run tests. Normalize to localhost.
QUEUE_URL="${QUEUE_URL/http:\/\/localstack:4566/http:\/\/localhost:4566}"
QUEUE_URL="${QUEUE_URL/http:\/\/127.0.0.1:4566/http:\/\/localhost:4566}"

export SQS_QUEUE_URL="${SQS_QUEUE_URL:-$QUEUE_URL}"
log "SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# --- Pipenv robustness ---
# Keep venv local to the repo, avoid relying on any shared/system site-packages.
export PIPENV_VENV_IN_PROJECT="${PIPENV_VENV_IN_PROJECT:-1}"

# --- Run behave from REPO ROOT (fixes "No steps directory ... localstack/tests/...") ---
cd "${REPO_ROOT}"

if ! command -v pipenv >/dev/null 2>&1; then
  log "ERROR: pipenv is not installed on this machine."
  log "Install it (example): pip install --user pipenv:  or  brew install pipenv"
  exit 1
fi

log "Installing python deps via pipenv (host)..."
# Use sync if lock exists; fall back to install if not.
if [[ -f "${REPO_ROOT}/Pipfile.lock" ]]; then
  pipenv sync --dev
else
  pipenv install --dev
fi

mkdir -p "${REPO_ROOT}/reports"

log "Running behave..."
pipenv run behave tests/component/features \
  --format=json.pretty \
  --outfile=./reports/cucumber.json

log "Done. Report: ${REPO_ROOT}/reports/cucumber.json"
