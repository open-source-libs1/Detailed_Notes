#!/usr/bin/env bash
set -euo pipefail

log() { echo "[component] $*"; }

# Always run from the folder where this script lives (localstack/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present (may contain proxy/cert values for containers)
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

# ---- LocalStack endpoint (HOST-run tests talk to localhost) ----
ENDPOINT="${ENDPOINT:-http://localhost:4566}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# Dummy creds for LocalStack (prevents boto3 trying real creds)
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN:-test}"

# Make sure boto3/botocore uses LocalStack for SQS
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-$ENDPOINT}"
export AWS_ENDPOINT_URL_SQS="${AWS_ENDPOINT_URL_SQS:-$ENDPOINT}"

# Avoid proxies breaking localhost/localstack calls
export NO_PROXY="${NO_PROXY:-}127.0.0.1,localhost,localstack"
export no_proxy="${no_proxy:-$NO_PROXY}"

# ---- CA bundle for HOST pip/pipenv/boto3 ----
# Your host path (from your screenshots). Override if needed.
HOST_CA_BUNDLE="${HOST_CA_BUNDLE:-$HOME/certs/C1G2RootCA.crt}"
if [[ -f "$HOST_CA_BUNDLE" ]]; then
  export HOST_CA_BUNDLE
  export AWS_CA_BUNDLE="$HOST_CA_BUNDLE"
  export REQUESTS_CA_BUNDLE="$HOST_CA_BUNDLE"
  export CURL_CA_BUNDLE="$HOST_CA_BUNDLE"
  export SSL_CERT_FILE="$HOST_CA_BUNDLE"
  export PIP_CERT="$HOST_CA_BUNDLE"
  log "Using HOST CA bundle: $HOST_CA_BUNDLE"
else
  log "WARNING: HOST_CA_BUNDLE not found at: $HOST_CA_BUNDLE"
  log "If pipenv install fails with TLS errors, set HOST_CA_BUNDLE to your real cert path."
fi

# ---- Required env expected by behave's environment.py ----
export ENVIRONMENT="${ENVIRONMENT:-local}"

# ---- DB (tests run on HOST; use localhost even if .env has host.docker.internal) ----
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

log "DB effective config: host=$DB_HOST port=$DB_PORT db=$DB_NAME user=$DB_USER"

# ---- Wait for LocalStack to be healthy ----
log "Waiting for LocalStack bootstrap to be healthy..."
for _ in {1..60}; do
  if curl -fsS "$ENDPOINT/_localstack/health" >/dev/null 2>&1; then
    log "LocalStack is healthy."
    break
  fi
  sleep 2
done

# ---- Resolve queue URL (default sqsq2; override with QUEUE_NAME=sqsq1 if needed) ----
QUEUE_NAME="${QUEUE_NAME:-sqsq2}"
log "Resolving QueueUrl for $QUEUE_NAME..."
SQS_QUEUE_URL="$(aws --endpoint-url="$ENDPOINT" sqs get-queue-url \
  --queue-name "$QUEUE_NAME" --query 'QueueUrl' --output text)"
export SQS_QUEUE_URL
log "SQS_QUEUE_URL=$SQS_QUEUE_URL"

# ---- Install deps + run behave ----
mkdir -p ./reports

log "Installing python deps via pipenv (host)..."
pipenv install --dev

log "Running behave..."
pipenv run behave tests/component/features --format=json.pretty --outfile=./reports/cucumber.json
