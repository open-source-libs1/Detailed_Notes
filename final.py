#!/usr/bin/env bash
set -euo pipefail

# ======================================================================================
# run.sh
# One entrypoint for local usage:
#   ./run.sh up                 -> build lambda zip(s) + docker compose up --build
#   ./run.sh down               -> docker compose down
#   ./run.sh logs localstack    -> tail localstack logs
#   ./run.sh logs enrollment-writer
#   ./run.sh test sqs1          -> send sample msg to sqsq1 (triggers qsink lambda)
#   ./run.sh test sqs2          -> send sample msg to sqsq2 (direct to enrollment-writer)
#   ./run.sh component-test     -> run behave component tests locally (host)
# ======================================================================================

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

usage() {
  cat <<EOF
Usage:
  ./run.sh up
  ./run.sh down
  ./run.sh logs localstack|enrollment-writer
  ./run.sh test sqs1|sqs2
  ./run.sh component-test

Notes:
  - Ensure localstack/.env is present and correct.
  - 'up' builds lambda ZIPs on host and mounts them into LocalStack.
EOF
}

cmd="${1:-}"

case "${cmd}" in
  up)
    echo "[run] PWD=$(pwd)"
    echo "[run] Building lambda ZIP(s) locally..."
    ./build_lambdas.sh

    echo "[run] Starting docker compose..."
    docker compose up --build
    ;;
  down)
    docker compose down
    ;;
  logs)
    target="${2:-}"
    if [ -z "${target}" ]; then usage; exit 1; fi
    docker compose logs -f "${target}"
    ;;
  test)
    which="${2:-}"
    if [ "${which}" = "sqs1" ]; then
      ./test_sqs1.sh
    elif [ "${which}" = "sqs2" ]; then
      ./test_sqs2.sh
    else
      usage
      exit 1
    fi
    ;;
  component-test)
    ./component_tests.sh
    ;;
  *)
    usage
    exit 1
    ;;
esac






//////////////////////



#!/usr/bin/env bash
set -euo pipefail

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

# Load env (names/region)
set -a
# shellcheck disable=SC1091
source ./.env
set +a

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "[test_sqs1] Waiting for LocalStack to be ready..."
until curl -fsS "${ENDPOINT}/health" >/dev/null 2>&1; do
  sleep 1
done

QSINK_URL="$(aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
  --queue-name "${QSINK_QUEUE_NAME}" --region "${REGION}" \
  --query QueueUrl --output text)"

echo "[test_sqs1] QSINK queue url: ${QSINK_URL}"

# Minimal BANK payload (matches your handler's required fields)
BODY='{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","program_code":"3882","source_id":"BANK","is_enrollment_active":true}'

aws --endpoint-url="${ENDPOINT}" sqs send-message \
  --queue-url "${QSINK_URL}" \
  --message-body "${BODY}" \
  --region "${REGION}" >/dev/null

echo "[test_sqs1] Sent message to ${QSINK_QUEUE_NAME}."
echo "[test_sqs1] Now tail logs:"
echo "  ./run.sh logs localstack"
echo "  ./run.sh logs enrollment-writer"






//////////////////////




#!/usr/bin/env bash
set -euo pipefail

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

set -a
# shellcheck disable=SC1091
source ./.env
set +a

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "[test_sqs2] Waiting for LocalStack to be ready..."
until curl -fsS "${ENDPOINT}/health" >/dev/null 2>&1; do
  sleep 1
done

ENR_URL="$(aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
  --queue-name "${ENROLLMENT_QUEUE_NAME}" --region "${REGION}" \
  --query QueueUrl --output text)"

echo "[test_sqs2] Enrollment queue url: ${ENR_URL}"

BODY='{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","program_code":"3882","source_id":"BANK","is_enrollment_active":true}'

aws --endpoint-url="${ENDPOINT}" sqs send-message \
  --queue-url "${ENR_URL}" \
  --message-body "${BODY}" \
  --region "${REGION}" >/dev/null

echo "[test_sqs2] Sent message to ${ENROLLMENT_QUEUE_NAME}."
echo "[test_sqs2] Tail logs:"
echo "  ./run.sh logs enrollment-writer"





///////////////////////////////////////



#!/usr/bin/env bash
set -euo pipefail

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE_DIR}/.." && pwd)"
cd "${HERE_DIR}"

set -a
# shellcheck disable=SC1091
source ./.env
set +a

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "[component-test] Ensuring LocalStack is up..."
until curl -fsS "${ENDPOINT}/health" >/dev/null 2>&1; do
  sleep 1
done

# Use the enrollment queue URL for tests
SQS_QUEUE_URL="$(aws --endpoint-url="${ENDPOINT}" sqs get-queue-url \
  --queue-name "${ENROLLMENT_QUEUE_NAME}" --region "${REGION}" \
  --query QueueUrl --output text)"

echo "[component-test] Using SQS_QUEUE_URL=${SQS_QUEUE_URL}"

# Mirror your existing test script envs but for LocalStack
export ENVIRONMENT=local
export AWS_DEFAULT_REGION="${REGION}"
export SQS_QUEUE_URL="${SQS_QUEUE_URL}"

# DB values (from .env)
export DB_NAME="${DB_NAME}"
export DB_HOST="${DB_HOST}"
export DB_USER="${DB_USER}"
export DB_PASSWORD="${DB_PASSWORD}"
export DB_PORT="${DB_PORT}"

cd "${REPO_ROOT}"

echo "[component-test] Running behave..."
pipenv run behave tests/component/features --format=json.pretty --outfile=./reports/cucumber.json
echo "[component-test] Done. Report: ./reports/cucumber.json"





///////////////////////////



# LocalStack – ReferralPlatform Enrollment (Local)

## What this setup does
This folder provides a repeatable local environment using LocalStack Pro:
- Creates S3 bucket, two SQS queues, and a Secrets Manager secret
- Deploys the QSink forwarder lambda (host-built ZIP)
- Connects SQS queue `sqsq1` -> QSink lambda (event source mapping)
- Runs `enrollment-writer` container only after LocalStack bootstrap is complete

**Important:** We do not modify application code (qsink lambda or enrollment writer).  
All changes are isolated to the `localstack/` folder.

---

## Prerequisites
- Docker Desktop running
- `aws` CLI installed
- `pipenv` installed
- Access to internal registries (LocalStack Pro image + lambda runtime mapping image)
- Corporate certs available at: `$HOME/certs/C1G2RootCA.crt`

---

## Files
- `.env` : single source of truth for names/DB/proxy/certs
- `build_lambdas.sh` : builds lambda ZIPs on host (robust install --target)
- `00-enrollment-init.sh` : LocalStack bootstrap (idempotent resource creation)
- `docker-compose.yml` : LocalStack + enrollment-writer wiring, health gating
- `run.sh` : one command entrypoint + testing helpers
- `test_sqs1.sh` : send message to sqsq1 (QSink input)
- `test_sqs2.sh` : send message to sqsq2 (EnrollmentWriter input)
- `component_tests.sh` : runs behave component tests against local stack

---

## How to run

### 1) Start stack (build zips + compose up)
From `localstack/`:
```bash
./run.sh up




./run.sh logs localstack
./run.sh logs enrollment-writer



./run.sh test sqs1
./run.sh test sqs2


./run.sh component-test

docker compose logs -f localstack


aws --endpoint-url=http://localhost:4566 secretsmanager list-secrets
aws --endpoint-url=http://localhost:4566 sqs list-queues
aws --endpoint-url=http://localhost:4566 s3 ls
aws --endpoint-url=http://localhost:4566 lambda list-functions


./run.sh down





