
#!/usr/bin/env bash
set -euo pipefail

# Runs behave component tests from the HOST.
# - Waits for LocalStack container health.
# - Fixes CA bundle paths for HOST (macOS) installs.
# - Ensures "behave" exists (installs if missing) without changing repo files.

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Load localstack env (queues/DB/region/etc.)
set -a
# shellcheck disable=SC1090
. "${HERE_DIR}/.env"
set +a

# ---- HOST CA bundle handling (pipenv runs on host, not inside container) ----
HOST_CA="${HOME}/certs/C1G2RootCA.crt"
if [[ -f "${HOST_CA}" ]]; then
  echo "[component] Using HOST CA bundle: ${HOST_CA}"
  export REQUESTS_CA_BUNDLE="${HOST_CA}"
  export CURL_CA_BUNDLE="${HOST_CA}"
  export NODE_EXTRA_CA_CERTS="${HOST_CA}"
else
  echo "[component] WARN: Host CA bundle not found at ${HOST_CA}. Unsetting CA bundle envs for host installs."
  unset REQUESTS_CA_BUNDLE CURL_CA_BUNDLE NODE_EXTRA_CA_CERTS
fi

LOCALSTACK_CONTAINER="${LOCALSTACK_CONTAINER:-localstack-enrollment}"

echo "[component] Waiting for LocalStack bootstrap to be healthy..."
until [[ "$(docker inspect -f '{{.State.Health.Status}}' "${LOCALSTACK_CONTAINER}" 2>/dev/null || echo "starting")" == "healthy" ]]; do
  sleep 2
done
echo "[component] LocalStack is healthy."

ENDPOINT="${ENDPOINT_HOST:-http://localhost:4566}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
AWS_CMD=(aws --endpoint-url="${ENDPOINT}" --region "${REGION}")

# Resolve enrollment queue URL for tests
QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${QUEUE_NAME}" --query 'QueueUrl' --output text)"
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#\\\/#/#g; s#\\##g')"
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#http://localstack:4566#http://localhost:4566#g; s#https://localstack:4566#http://localhost:4566#g')"

mkdir -p "${HERE_DIR}/reports"

# Export env vars used by component tests
export ENVIRONMENT=local
export AWS_DEFAULT_REGION="${REGION}"
export SQS_QUEUE_URL="${QUEUE_URL}"

export DB_NAME="${DB_NAME}"
export DB_HOST="${DB_HOST}"
export DB_USER="${DB_USER}"
export DB_PASSWORD="${DB_PASSWORD}"
export DB_PORT="${DB_PORT}"

echo "[component] Installing python deps via pipenv (host)..."
# Use --dev in case behave lives under dev-packages
pipenv install --dev

# ---- Ensure behave exists (do NOT change repo; install into venv if missing) ----
if ! pipenv run python -c "import behave" >/dev/null 2>&1; then
  echo "[component] 'behave' not found in venv. Installing behave into Pipenv environment..."
  pipenv run pip install -q behave
fi

# Prefer python -m behave so we don't rely on PATH resolution for the entrypoint
echo "[component] Running behave..."
pipenv run python -m behave tests/component/features \
  --format=json.pretty \
  --outfile="${HERE_DIR}/reports/cucumber.json"

echo "[component] Done. Report: ${HERE_DIR}/reports/cucumber.json"
