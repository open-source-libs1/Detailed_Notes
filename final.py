echo "[test_sqs1] Sending message..."

# IMPORTANT:
#  - no >/dev/null
#  - use --query + --output text so we get clean tokens (no JSON parsing needed)
SEND_OUT="$("${AWS_CMD[@]}" sqs send-message \
  --queue-url "${QUEUE_URL}" \
  --message-body "${BODY}" \
  --query '[MessageId,MD5OfMessageBody]' \
  --output text
)"

echo "[test_sqs1] send-message raw output: ${SEND_OUT:-<EMPTY>}"

MSG_ID="$(printf '%s' "$SEND_OUT" | awk '{print $1}')"
MD5="$(printf '%s' "$SEND_OUT" | awk '{print $2}')"

echo "[test_sqs1] Sent"
echo "[test_sqs1] MessageId=${MSG_ID:-<EMPTY>}"
echo "[test_sqs1] MD5OfMessageBody=${MD5:-<EMPTY>}"
