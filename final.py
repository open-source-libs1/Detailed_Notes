#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# Component tests runner (host execution)
#
# One-command goal:
#   ./run.sh test component
#
# Key ideas:
# - behave/pipenv runs on your HOST machine (not inside docker)
# - therefore the AWS SDK endpoint MUST be "localhost:4566"
#   (NOT "localstack:4566" which only resolves inside docker network)
# - resolve SQS QueueUrl dynamically from LocalStack
# - configure corporate CA bundle automatically (no manual export)
# ------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[component] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[component] REPO_ROOT=${REPO_ROOT}"

# Load LocalStack env (optional)
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  echo "[component] Loading ${ENV_FILE}"
  # Export non-comment, non-empty lines
  # shellcheck disable=SC2046
  export $(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$' | xargs -0 2>/dev/null || true) || true
else
  echo "[component] NOTE: ${ENV_FILE} not found; continuing with existing shell env."
fi

# ---- LocalStack endpoint for HOST-run tests ----
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Avoid corporate proxy interfering with localhost calls
export NO_PROXY="${NO_PROXY:-},localhost,127.0.0.1"
export no_proxy="${no_proxy:-},localhost,127.0.0.1"

# LocalStack dummy credentials
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-${AWS_REGION}}"

# Common endpoint envs (helps internal wrappers too)
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-${ENDPOINT}}"
export AWS_ENDPOINT_URL_SQS="${AWS_ENDPOINT_URL_SQS:-${ENDPOINT}}"

echo "[component] Using endpoint: ${ENDPOINT}"
echo "[component] Using region:   ${AWS_DEFAULT_REGION}"
echo "[component] NO_PROXY:       ${NO_PROXY}"

# ---- DB config (host-run) ----
DB_NAME="${DB_NAME:-referrals_db}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"
DB_PORT="${DB_PORT:-29464}"
DB_HOST="${DB_HOST:-localhost}"

# If .env is tuned for containers, override for host-run
if [[ "${DB_HOST}" == "host.docker.internal" ]]; then
  echo "[component] NOTE: DB_HOST=host.docker.internal is for containers. Overriding to localhost for host-run tests."
  DB_HOST="localhost"
fi

export DB_NAME DB_USER DB_PASSWORD DB_PORT DB_HOST

echo "[component] DB effective config: host=${DB_HOST} port=${DB_PORT} db=${DB_NAME} user=${DB_USER}"

# ---- Resolve SQS queue URL from LocalStack ----
QUEUE_NAME="${COMPONENT_TEST_QUEUE_NAME:-sqsq2}"

echo "[component] Resolving QueueUrl for ${QUEUE_NAME}..."
SQS_QUEUE_URL="$(
  aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
    --queue-name "${QUEUE_NAME}" \
    --query 'QueueUrl' \
    --output text
)"

if [[ -z "${SQS_QUEUE_URL}" || "${SQS_QUEUE_URL}" == "None" ]]; then
  echo "[component] ERROR: Could not resolve QueueUrl for ${QUEUE_NAME}. Is LocalStack up and bootstrap complete?"
  echo "[component] Try: docker compose ps && docker logs localstack-enrollment"
  exit 1
fi

export SQS_QUEUE_URL="${SQS_QUEUE_URL}"
echo "[component] SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# ---- Corporate TLS CA bundle (host-run) ----
# Your earlier failure happened because pipenv/pip was pointed to a *container* path like /root/certs/...
# Here we choose a HOST path automatically so pipenv can install from Artifactory.

pick_ca_bundle() {
  # If user already exported one, keep it.
  if [[ -n "${HOST_CA_BUNDLE:-}" && -f "${HOST_CA_BUNDLE}" ]]; then
    echo "${HOST_CA_BUNDLE}"
    return 0
  fi

  # Common corporate paths (edit/add if your org uses something else)
  local candidates=(
    "${HOME}/certs/C1G2RootCA.crt"
    "${HOME}/certs/C1G2RootCA.pem"
    "${HOME}/certs/ca-bundle.crt"
    "/etc/ssl/cert.pem"                 # macOS system bundle (fallback)
    "/etc/ssl/certs/ca-certificates.crt" # linux fallback
  )

  local c
  for c in "${candidates[@]}"; do
    if [[ -f "${c}" ]]; then
      echo "${c}"
      return 0
    fi
  done

  # No file found
  return 1
}

if CA_BUNDLE_PATH="$(pick_ca_bundle)"; then
  echo "[component] Using HOST CA bundle: ${CA_BUNDLE_PATH}"
  export REQUESTS_CA_BUNDLE="${CA_BUNDLE_PATH}"
  export PIP_CERT="${CA_BUNDLE_PATH}"
else
  echo "[component] WARN: No host CA bundle found."
  echo "[component] WARN: If pipenv fails to reach Artifactory, create ${HOME}/certs/C1G2RootCA.crt"
  echo "[component] WARN: Or export HOST_CA_BUNDLE=/path/to/your/ca.crt and re-run."
fi

# ---- Run tests ----
cd "${REPO_ROOT}"

echo "[component] Installing python deps via pipenv (host)..."
if [[ -f "Pipfile.lock" ]]; then
  pipenv sync --dev
else
  pipenv install --dev
fi

echo "[component] Running behave..."
mkdir -p reports
pipenv run behave tests/component/features --format=json.pretty --outfile=./reports/cucumber.json

echo "[component] Done. Report: reports/cucumber.json"
