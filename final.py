#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------
# Single entrypoint script for local workflow.
#
# Usage:
#   ./run.sh                      # build zips + docker compose up --build
#   ./run.sh up                   # same as default
#   ./run.sh down                 # docker compose down -v
#   ./run.sh build                # build lambda zips only
#   ./run.sh logs [service]       # follow logs (optional service)
#   ./run.sh test sqs1            # send test message to sqsq1
#   ./run.sh test sqs2            # send test message to sqsq2
#   ./run.sh test component       # run behave component tests (host)
# ---------------------------------------------

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

cmd="${1:-up}"
sub="${2:-}"
sub2="${3:-}"

case "${cmd}" in
  up|"")
    echo "[run] PWD=$(pwd)"
    echo "[run] Building lambda ZIP(s) locally..."
    ./build_lambdas.sh

    echo "[run] Starting docker compose..."
    docker compose up --build
    ;;

  down)
    echo "[run] Stopping stack..."
    docker compose down -v
    ;;

  build)
    echo "[run] Building lambda ZIP(s) locally..."
    ./build_lambdas.sh
    ;;

  logs)
    if [[ -n "${sub}" ]]; then
      docker compose logs -f "${sub}"
    else
      docker compose logs -f
    fi
    ;;

  test)
    case "${sub}" in
      sqs1) ./test_sqs1.sh ;;
      sqs2) ./test_sqs2.sh ;;
      component) ./component_tests.sh ;;
      *)
        echo "Unknown test: ${sub}"
        echo "Use: ./run.sh test {sqs1|sqs2|component}"
        exit 1
        ;;
    esac
    ;;

  *)
    echo "Unknown command: ${cmd}"
    echo "Try: ./run.sh up | down | build | logs | test"
    exit 1
    ;;
esac





//////////////////////////



#!/usr/bin/env bash
set -euo pipefail

# Sends a sample message to QSINK_QUEUE_NAME (sqsq1)

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
QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"

AWS_CMD=(aws --endpoint-url="${ENDPOINT}")

echo "[test_sqs1] Resolving QueueUrl for ${QUEUE_NAME}..."
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${QUEUE_NAME}" --query 'QueueUrl' --output text)"

# Normalize for host use (LocalStack sometimes returns http://localstack:4566/...)
QUEUE_URL="${QUEUE_URL/http:\/\/localstack:4566/http:\/\/localhost:4566}"

echo "[test_sqs1] QueueUrl=${QUEUE_URL}"

BODY='{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","sor_id":"185","is_enrollment_active":true,"program_code":"3882","source_id":"BANK"}'

echo "[test_sqs1] Sending message..."
"${AWS_CMD[@]}" sqs send-message --queue-url "${QUEUE_URL}" --message-body "${BODY}" >/dev/null

echo "[test_sqs1] Done."





////////////////////////////////////////



#!/usr/bin/env bash
set -euo pipefail

# Sends a sample message directly to ENROLLMENT_QUEUE_NAME (sqsq2)

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
QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

AWS_CMD=(aws --endpoint-url="${ENDPOINT}")

echo "[test_sqs2] Resolving QueueUrl for ${QUEUE_NAME}..."
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${QUEUE_NAME}" --query 'QueueUrl' --output text)"
QUEUE_URL="${QUEUE_URL/http:\/\/localstack:4566/http:\/\/localhost:4566}"

echo "[test_sqs2] QueueUrl=${QUEUE_URL}"

BODY='{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","sor_id":"185","is_enrollment_active":true,"program_code":"3882","source_id":"BANK"}'

echo "[test_sqs2] Sending message..."
"${AWS_CMD[@]}" sqs send-message --queue-url "${QUEUE_URL}" --message-body "${BODY}" >/dev/null

echo "[test_sqs2] Done."





////////////////////



#!/usr/bin/env bash
set -euo pipefail

# Runs behave component tests from the HOST.
# Assumes:
#  - enrollment-writer container is running (docker compose up)
#  - LocalStack bootstrap is healthy
#  - You have pipenv installed on host

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Load local env for DB + region + queue names
set -a
# shellcheck disable=SC1090
. "${HERE_DIR}/.env"
set +a

LOCALSTACK_CONTAINER="${LOCALSTACK_CONTAINER:-localstack-enrollment}"

echo "[component] Waiting for LocalStack bootstrap to be healthy..."
until [[ "$(docker inspect -f '{{.State.Health.Status}}' "${LOCALSTACK_CONTAINER}" 2>/dev/null || echo "starting")" == "healthy" ]]; do
  sleep 2
done
echo "[component] LocalStack is healthy."

ENDPOINT="${ENDPOINT_HOST:-http://localhost:4566}"
AWS_CMD=(aws --endpoint-url="${ENDPOINT}")

# Resolve enrollment queue URL for tests if your test runner needs it
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${ENROLLMENT_QUEUE_NAME}" --query 'QueueUrl' --output text)"
QUEUE_URL="${QUEUE_URL/http:\/\/localstack:4566/http:\/\/localhost:4566}"

mkdir -p "${HERE_DIR}/reports"

export ENVIRONMENT=local
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export SQS_QUEUE_URL="${QUEUE_URL}"

# DB vars used by tests (based on your screenshot pattern)
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

