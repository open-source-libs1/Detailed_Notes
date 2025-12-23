curl -s http://localhost:4566/_localstack/health | head

aws --endpoint-url=http://localhost:4566 --region us-east-1 sqs list-queues

aws --endpoint-url=http://localhost:4566 --region us-east-1 lambda list-functions

aws --endpoint-url=http://localhost:4566 --region us-east-1 lambda list-event-source-mappings \
  --function-name qsink-forwarder-lambda


docker exec -it localstack-enrollment awslocal sqs list-queues
docker exec -it localstack-enrollment awslocal lambda list-functions
docker exec -it localstack-enrollment awslocal lambda list-event-source-mappings --function-name qsink-forwarder-lambda


////////////////////


#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# test_sqs1.sh
# Sends a sample message to SQSQ1 (qsink queue) and prints MessageId + MD5.
# Works on host even if "awslocal" is NOT installed.
# =============================================================================

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load optional env (same pattern used elsewhere)
ENV_FILE="${HERE_DIR}/.env.localstack"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"

AWS_CMD=(aws --endpoint-url="${ENDPOINT}" --region "${REGION}")

echo "[test_sqs1] ENDPOINT=${ENDPOINT}"
echo "[test_sqs1] REGION=${REGION}"
echo "[test_sqs1] QUEUE_NAME=${QUEUE_NAME}"

echo "[test_sqs1] Resolving QueueUrl..."
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${QUEUE_NAME}" --query 'QueueUrl' --output text)"

# Normalize if LocalStack returns internal hostname
QUEUE_URL="$(printf "%s" "${QUEUE_URL}" | sed 's#http://localstack:4566#http://localhost:4566#g')"
echo "[test_sqs1] QueueUrl=${QUEUE_URL}"

# Your sample payload (keep it consistent with what qsink expects)
BODY='{"version":2,"batchMeta":{"schemaId":"batest.test_schema","region":"1","test":"integration"},"records":[{"meta":{"schema":"gen3.enrollment","source":"BANK"},"payload":{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","sor_id":"185","is_enrollment_active":true,"program_code":"3882","source_id":"BANK"}}]}'

echo "[test_sqs1] Sending message..."
SEND_OUT="$("${AWS_CMD[@]}" sqs send-message --queue-url "${QUEUE_URL}" --message-body "${BODY}" --output json)"

MSG_ID="$(python - <<PY
import json,sys
d=json.loads(sys.argv[1])
print(d.get("MessageId",""))
PY
"${SEND_OUT}")"

MD5="$(python - <<PY
import json,sys
d=json.loads(sys.argv[1])
print(d.get("MD5OfMessageBody",""))
PY
"${SEND_OUT}")"

echo "[test_sqs1] ✅ Sent"
echo "[test_sqs1] MessageId=${MSG_ID}"
echo "[test_sqs1] MD5OfMessageBody=${MD5}"

echo "[test_sqs1] Tip: watch localstack logs for invocation:"
echo "  docker logs -f localstack-enrollment | egrep -i 'qsink-forwarder-lambda|error|invoke|sqs_poller|event source' || true"





/////////////////////////////////


#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# test_sqs2.sh
# Sends a sample message directly to SQSQ2 (enrollment queue) and prints MessageId.
# Works on host even if "awslocal" is NOT installed.
# =============================================================================

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_FILE="${HERE_DIR}/.env.localstack"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

AWS_CMD=(aws --endpoint-url="${ENDPOINT}" --region "${REGION}")

echo "[test_sqs2] ENDPOINT=${ENDPOINT}"
echo "[test_sqs2] REGION=${REGION}"
echo "[test_sqs2] QUEUE_NAME=${QUEUE_NAME}"

echo "[test_sqs2] Resolving QueueUrl..."
QUEUE_URL="$("${AWS_CMD[@]}" sqs get-queue-url --queue-name "${QUEUE_NAME}" --query 'QueueUrl' --output text)"
QUEUE_URL="$(printf "%s" "${QUEUE_URL}" | sed 's#http://localstack:4566#http://localhost:4566#g')"
echo "[test_sqs2] QueueUrl=${QUEUE_URL}"

# This is the payload enrollment-writer expects (your earlier example)
BODY='{"account_key":"820856933390","account_key_type":"TOKENIZEDBAN","sor_id":"185","is_enrollment_active":true,"program_code":"3882","source_id":"BANK"}'

echo "[test_sqs2] Sending message..."
SEND_OUT="$("${AWS_CMD[@]}" sqs send-message --queue-url "${QUEUE_URL}" --message-body "${BODY}" --output json)"

MSG_ID="$(python - <<PY
import json,sys
d=json.loads(sys.argv[1])
print(d.get("MessageId",""))
PY
"${SEND_OUT}")"

MD5="$(python - <<PY
import json,sys
d=json.loads(sys.argv[1])
print(d.get("MD5OfMessageBody",""))
PY
"${SEND_OUT}")"

echo "[test_sqs2] ✅ Sent"
echo "[test_sqs2] MessageId=${MSG_ID}"
echo "[test_sqs2] MD5OfMessageBody=${MD5}"

echo "[test_sqs2] Tip: watch enrollment-writer logs:"
echo "  docker logs -f enrollment-writer | egrep -i 'MessageId|processing|error|exception' || true"



///////////////////////


aws --endpoint-url=http://localhost:4566 --region us-east-1 lambda list-event-source-mappings --function-name qsink-forwarder-lambda

docker logs --tail=200 localstack-enrollment | egrep -i 'qsink-forwarder-lambda|ImportModuleError|No module named|sqs_poller|event source|error'


