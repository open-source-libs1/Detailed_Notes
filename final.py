#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log "SCRIPT_DIR=${SCRIPT_DIR}"
log "REPO_ROOT=${REPO_ROOT}"

# Load localstack/.env if present (keeps your existing config)
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; source "${SCRIPT_DIR}/.env"; set +a
  log "Loaded ${SCRIPT_DIR}/.env"
fi

# ---------- Endpoint selection (host-run component tests must hit localhost) ----------
LS_PORT="${EDGE_PORT:-4566}"
LS_HOST="${LOCALSTACK_HOST:-localstack}"

# If we are NOT inside a container, always use localhost to reach LocalStack.
if [[ ! -f "/.dockerenv" ]]; then
  LS_HOST="localhost"
fi

ENDPOINT="${AWS_ENDPOINT_URL:-http://${LS_HOST}:${LS_PORT}}"
ENDPOINT="${ENDPOINT%/}"

log "Using endpoint: ${ENDPOINT}"
log "Using region:   ${AWS_DEFAULT_REGION:-us-east-1}"

export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_REGION="${AWS_DEFAULT_REGION}"
export ENVIRONMENT="${ENVIRONMENT:-local}"

# Boto3 endpoint discovery in your tests is coming from env; set both to be safe.
export AWS_ENDPOINT_URL="${ENDPOINT}"
export AWS_ENDPOINT_URL_SQS="${ENDPOINT}"

# Make sure localstack/localhost bypass proxy
export NO_PROXY="${NO_PROXY:-},127.0.0.1,localhost,localstack"

# ---------- Host CA bundle baked into the script ----------
HOST_CA_BUNDLE="${HOST_CA_BUNDLE:-${HOME}/certs/C1G2RootCA.crt}"
log "Using HOST CA bundle: ${HOST_CA_BUNDLE}"

# Cover common tooling (pip/pipenv/requests/curl)
export REQUESTS_CA_BUNDLE="${HOST_CA_BUNDLE}"
export AWS_CA_BUNDLE="${HOST_CA_BUNDLE}"
export SSL_CERT_FILE="${HOST_CA_BUNDLE}"
export CURL_CA_BUNDLE="${HOST_CA_BUNDLE}"
export PIP_CERT="${HOST_CA_BUNDLE}"

# ---------- DB_HOST override for host-run tests ----------
# Your app containers use host.docker.internal; host-run tests should use localhost.
if [[ "${DB_HOST:-}" == "host.docker.internal" ]]; then
  log "NOTE: DB_HOST=host.docker.internal is for containers. Overriding to localhost for host-run tests."
  export DB_HOST="localhost"
fi

log "DB effective config: host=${DB_HOST:-} port=${DB_PORT:-} db=${DB_NAME:-} user=${DB_USER:-}"

# ---------- Wait for LocalStack to be ready ----------
log "Waiting for LocalStack bootstrap to be healthy..."
for _ in {1..120}; do
  if curl -fsS "${ENDPOINT}/_localstack/health" >/dev/null 2>&1; then
    log "LocalStack is healthy."
    break
  fi
  sleep 1
done

# ---------- Resolve QueueUrl (and de-escape / normalize host) ----------
QUEUE_NAME="${QUEUE_NAME:-sqsq2}"
log "Resolving QueueUrl for ${QUEUE_NAME}..."

SQS_QUEUE_URL="$(aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
  --queue-name "${QUEUE_NAME}" \
  --query 'QueueUrl' \
  --output text)"

# If anything ever returns escaped slashes (http:\/\/...), strip backslashes.
SQS_QUEUE_URL="${SQS_QUEUE_URL//\\/}"

# Force QueueUrl host to match ENDPOINT host (prevents 'could not connect' / mismatched host issues).
SQS_QUEUE_URL="$(echo "${SQS_QUEUE_URL}" | sed -E "s#^https?://[^/]+#${ENDPOINT}#")"

export SQS_QUEUE_URL
log "SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# ---------- Run component tests from repo root (so steps/ is found) ----------
cd "${REPO_ROOT}"

log "Installing python deps via pipenv (host)..."
pipenv install --dev

log "Running behave..."
mkdir -p reports
pipenv run behave tests/component/features --format=json.pretty --outfile=./reports/cucumber.json
