#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log "SCRIPT_DIR=${SCRIPT_DIR}"
log "REPO_ROOT=${REPO_ROOT}"

# ---- Load env (your logs show .env.localstack is the source of truth)
ENV_FILE=""
if [[ -f "${SCRIPT_DIR}/.env.localstack" ]]; then
  ENV_FILE="${SCRIPT_DIR}/.env.localstack"
elif [[ -f "${SCRIPT_DIR}/.env" ]]; then
  ENV_FILE="${SCRIPT_DIR}/.env"
else
  log "ERROR: No env file found at ${SCRIPT_DIR}/.env.localstack or ${SCRIPT_DIR}/.env"
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"
log "Loaded ${ENV_FILE}"

# ---- Hard requirements for tests
: "${ENVIRONMENT:?ENVIRONMENT must be set (e.g., local)}"
: "${AWS_DEFAULT_REGION:?AWS_DEFAULT_REGION must be set (e.g., us-east-1)}"
: "${DB_NAME:?DB_NAME must be set}"
: "${DB_HOST:?DB_HOST must be set}"
: "${DB_USER:?DB_USER must be set}"
: "${DB_PASSWORD:?DB_PASSWORD must be set}"
: "${DB_PORT:?DB_PORT must be set}"

# ---- Endpoint (host-run should use localhost)
AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localstack:4566}"

# Detect host-run (very simple heuristic; your logs already do this)
HOST_RUN="false"
if [[ "${AWS_ENDPOINT_URL}" == *"localstack"* ]]; then
  HOST_RUN="true"
  log "NOTE: Host-run detected; normalizing AWS_ENDPOINT_URL localstack->localhost"
  AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL//localstack/localhost}"
fi

export AWS_ENDPOINT_URL
export AWS_REGION="${AWS_DEFAULT_REGION}"
export AWS_DEFAULT_REGION

# Make boto3/CLI consistently hit LocalStack
export AWS_ENDPOINT_URL_SQS="${AWS_ENDPOINT_URL}"
export AWS_EC2_METADATA_DISABLED="true"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN:-}"

# Proxy bypass (common corporate issue)
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,localstack,host.docker.internal}"
export no_proxy="${no_proxy:-$NO_PROXY}"

# ---- CA bundle: keep it inside the script (no Terminal export needed)
# Your logs show: "Using HOST CA bundle: /Users/.../C1G2RootCA.crt"
if [[ -n "${HOST_CA_BUNDLE:-}" ]]; then
  export AWS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export REQUESTS_CA_BUNDLE="${HOST_CA_BUNDLE}"
  export SSL_CERT_FILE="${HOST_CA_BUNDLE}"
  log "Using HOST CA bundle: ${HOST_CA_BUNDLE}"
else
  log "WARN: HOST_CA_BUNDLE is not set; continuing without custom CA bundle"
fi

# ---- DB host override note (matches your log behavior)
if [[ "${DB_HOST}" == "host.docker.internal" ]]; then
  log "NOTE: DB_HOST=host.docker.internal is for containers. Overriding to localhost for host-run tests."
  DB_HOST="localhost"
fi
export DB_HOST

log "DB effective config: host=${DB_HOST} port=${DB_PORT} db=${DB_NAME} user=${DB_USER}"

# ---- IMPORTANT: Do NOT health-check LocalStack (per your requirement)
# We ONLY print diagnostics best-effort.

# ---- Queue URL: use existing env var; do NOT resolve via awslocal/aws unless missing
# Your .env.localstack currently exports:
#   SQS_QUEUE_URL="http://localstack:4566/queue/us-east-1/000000000000/sqsq2"
# On host-run, "localstack" hostname is usually NOT resolvable, so normalize to localhost.
if [[ -z "${SQS_QUEUE_URL:-}" ]]; then
  log "ERROR: SQS_QUEUE_URL is not set in ${ENV_FILE}."
  log "Set it to: http://localstack:4566/queue/us-east-1/000000000000/sqsq2 (container) OR http://localhost:4566/queue/us-east-1/000000000000/sqsq2 (host)"
  exit 1
fi

if [[ "${HOST_RUN}" == "true" ]]; then
  # normalize only the hostname part
  SQS_QUEUE_URL="${SQS_QUEUE_URL//http:\/\/localstack:4566/http:\/\/localhost:4566}"
  SQS_QUEUE_URL="${SQS_QUEUE_URL//https:\/\/localstack:4566/https:\/\/localhost:4566}"
fi
export SQS_QUEUE_URL

# ---- Print env summary (what you asked for)
log "Env summary:"
log "  ENVIRONMENT=${ENVIRONMENT}"
log "  AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}"
log "  AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL}"
log "  AWS_ENDPOINT_URL_SQS=${AWS_ENDPOINT_URL_SQS}"
log "  SQS_QUEUE_URL=${SQS_QUEUE_URL}"
log "  DB_NAME=${DB_NAME}"
log "  DB_HOST=${DB_HOST}"
log "  DB_USER=${DB_USER}"
log "  DB_PASSWORD=${DB_PASSWORD}"
log "  DB_PORT=${DB_PORT}"
log "  HOST_CA_BUNDLE=${HOST_CA_BUNDLE:-}"

# ---- Best-effort: print queues (do not fail if aws cli isn't present)
if command -v aws >/dev/null 2>&1; then
  log "Listing queues (best-effort):"
  aws --endpoint-url "${AWS_ENDPOINT_URL}" sqs list-queues --output json || log "WARN: list-queues failed (continuing)"
else
  log "WARN: aws CLI not found; cannot list queues (continuing)"
fi

# ---- Run behave from repo root (Pipfile is at repo root per your logs)
cd "${REPO_ROOT}"
mkdir -p "${REPO_ROOT}/reports"

log "Installing python deps via pipenv (host)..."
export PIPENV_NOSPIN=1

log "Running behave..."
pipenv run behave tests/component/features \
  --format=json.pretty \
  --outfile=./reports/cucumber.json
