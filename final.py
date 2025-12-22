#!/usr/bin/env bash
set -euo pipefail

# Sends a sample message to QSINK_QUEUE_NAME (sqsq1)
# NOTE: This runs on HOST, so endpoint must be localhost:4566.

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

# Load .env
set -a
# shellcheck disable=SC1090
. ./.env
set +a

LOCALSTACK_CONTAINER="${LOCALSTACK_CONTAINER:-localstack-enrollment}"

echo "[test_sqs1] Waiting for LocalStack bootstrap to be healthy..."
until [[ "$(docker inspect -f '{{.State.Health.Status}}' "${LOCALSTACK_CONTAINER}" 2>/dev/null || echo "starting")" == "healthy" ]]; do
  sleep 2
done
echo "[test_sqs1] LocalStack is healthy."

ENDPOINT="${ENDPOINT_HOST:-http://localhost:4566}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"

AWS_CMD=(aws --endpoint-url="${ENDPOINT}" --region "${REGION}")

echo "[test_sqs1] Resolving QueueUrl for ${QUEUE_NAME}..."
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${QUEUE_NAME}" --query 'QueueUrl' --output text)"

# Normalize any escaped slashes and stray backslashes (some environments return http:\/\/...)
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#\\\/#/#g; s#\\##g')"

# If LocalStack returns an internal hostname, rewrite for host usage
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#http://localstack:4566#http://localhost:4566#g; s#https://localstack:4566#http://localhost:4566#g')"

echo "[test_sqs1] QueueUrl=${QUEUE_URL}"

BODY='{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","sor_id":"185","is_enrollment_active":true,"program_code":"3882","source_id":"BANK"}'

echo "[test_sqs1] Sending message..."
"${AWS_CMD[@]}" sqs send-message --queue-url "${QUEUE_URL}" --message-body "${BODY}" >/dev/null

echo "[test_sqs1] Done."





//////////////////////////////////////////


#!/usr/bin/env bash
set -euo pipefail

# Sends a sample message directly to ENROLLMENT_QUEUE_NAME (sqsq2)
# NOTE: This runs on HOST, so endpoint must be localhost:4566.

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

set -a
# shellcheck disable=SC1090
. ./.env
set +a

LOCALSTACK_CONTAINER="${LOCALSTACK_CONTAINER:-localstack-enrollment}"

echo "[test_sqs2] Waiting for LocalStack bootstrap to be healthy..."
until [[ "$(docker inspect -f '{{.State.Health.Status}}' "${LOCALSTACK_CONTAINER}" 2>/dev/null || echo "starting")" == "healthy" ]]; do
  sleep 2
done
echo "[test_sqs2] LocalStack is healthy."

ENDPOINT="${ENDPOINT_HOST:-http://localhost:4566}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

AWS_CMD=(aws --endpoint-url="${ENDPOINT}" --region "${REGION}")

echo "[test_sqs2] Resolving QueueUrl for ${QUEUE_NAME}..."
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${QUEUE_NAME}" --query 'QueueUrl' --output text)"

# Normalize any escaped slashes and stray backslashes
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#\\\/#/#g; s#\\##g')"

# Rewrite internal hostname -> host localhost
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#http://localstack:4566#http://localhost:4566#g; s#https://localstack:4566#http://localhost:4566#g')"

echo "[test_sqs2] QueueUrl=${QUEUE_URL}"

BODY='{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","sor_id":"185","is_enrollment_active":true,"program_code":"3882","source_id":"BANK"}'

echo "[test_sqs2] Sending message..."
"${AWS_CMD[@]}" sqs send-message --queue-url "${QUEUE_URL}" --message-body "${BODY}" >/dev/null

echo "[test_sqs2] Done."





//////////////////////////////////



#!/usr/bin/env bash
set -euo pipefail

# Runs behave component tests from the HOST.
# Important: .env contains container CA paths (/root/certs/...)
# but pipenv runs on macOS, so we must override CA bundle paths for HOST.

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Load local env (queues/DB/region/etc.)
set -a
# shellcheck disable=SC1090
. "${HERE_DIR}/.env"
set +a

# ---- FIX: CA bundle for HOST pip/pipenv ----
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
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${ENROLLMENT_QUEUE_NAME}" --query 'QueueUrl' --output text)"
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#\\\/#/#g; s#\\##g')"
QUEUE_URL="$(printf '%s' "${QUEUE_URL}" | sed 's#http://localstack:4566#http://localhost:4566#g; s#https://localstack:4566#http://localhost:4566#g')"

mkdir -p "${HERE_DIR}/reports"

export ENVIRONMENT=local
export AWS_DEFAULT_REGION="${REGION}"
export SQS_QUEUE_URL="${QUEUE_URL}"

# DB vars used by tests
export DB_NAME="${DB_NAME}"
export DB_HOST="${DB_HOST}"
export DB_USER="${DB_USER}"
export DB_PASSWORD="${DB_PASSWORD}"
export DB_PORT="${DB_PORT}"

echo "[component] Installing python deps via pipenv (host)..."
pipenv install

echo "[component] Running behave..."
pipenv run behave tests/component/features \
  --format=json.pretty \
  --outfile="${HERE_DIR}/reports/cucumber.json"

echo "[component] Done. Report: ${HERE_DIR}/reports/cucumber.json"


