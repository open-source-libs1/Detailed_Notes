# Capture send-message JSON output (keep your existing SEND_OUT assignment)
# SEND_OUT="$("${AWS_CMD[@]}" sqs send-message ... --output json)"

# Parse MessageId + MD5 safely from JSON via stdin (no argv, no command-not-found)
MSG_ID="$(python3 - <<'PY' <<<"$SEND_OUT"
import json, sys
d = json.load(sys.stdin)
print(d.get("MessageId", ""))
PY
)"

MD5="$(python3 - <<'PY' <<<"$SEND_OUT"
import json, sys
d = json.load(sys.stdin)
print(d.get("MD5OfMessageBody", ""))
PY
)"

echo "[test_sqs1] Sent"
echo "[test_sqs1] MessageId=${MSG_ID}"
echo "[test_sqs1] MD5OfMessageBody=${MD5}"
