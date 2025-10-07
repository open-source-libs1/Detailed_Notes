

import json
import logging
from typing import Any, List, Sequence, Tuple

logger = logging.getLogger(__name__)

# Public type aliases for clarity
MsgTuple = Tuple[str, Any]   # (messageId, payload_object)
InTuple  = Tuple[str, str]   # (messageId, body_json_string)


def extract_payloads(records: Sequence[InTuple]) -> List[MsgTuple]:
    """
    Extract payload objects from SQS body JSON strings.

    For each (messageId, body_json_string):
      1) Parse body_json_string (outer JSON).
      2) Expect body["records"] to be a list of objects with a `payload` field.
      3) `payload` must be a JSON string; parse it into an object.
      4) Return a flat list of (messageId, payload_object).

    Returns: [(messageId, payload_object)], skipping malformed entries with warnings.
    """
    out: List[MsgTuple] = []
    logger.debug("extract_payloads: starting with %d record(s)", len(records))

    for message_id, body_str in records:
        if not isinstance(message_id, str) or not isinstance(body_str, str):
            logger.warning(
                "Record (id=%s): expected (str, str), got (%s, %s); skipping",
                message_id, type(message_id).__name__, type(body_str).__name__,
            )
            continue

        try:
            body = json.loads(body_str)
        except (TypeError, ValueError) as e:
            logger.warning("Record (id=%s): body is not valid JSON; skipping (%s)", message_id, e)
            continue

        body_records = body.get("records")
        if not isinstance(body_records, list):
            logger.warning("Record (id=%s): 'records' missing or not a list; skipping", message_id)
            continue

        logger.debug("Record (id=%s): found %d inner record(s)", message_id, len(body_records))

        for rec in body_records:
            if not isinstance(rec, dict) or "payload" not in rec:
                logger.warning("Record (id=%s): missing/invalid 'payload'; skipping", message_id)
                continue

            raw = rec["payload"]
            if not isinstance(raw, str):
                logger.warning("Record (id=%s): payload is not a string; skipping", message_id)
                continue

            try:
                payload = json.loads(raw)
            except (TypeError, ValueError) as e:
                logger.warning("Record (id=%s): payload not valid JSON; skipping (%s)", message_id, e)
                continue

            out.append((message_id, payload))

    logger.debug("extract_payloads: extracted %d payload(s) total", len(out))
    return out


# ---- Serialization helpers (shared by handler/tests) ----

def to_json_bytes(obj: Any) -> bytes:
    """
    Convert an object to compact JSON UTF-8 bytes.
    - Use for Kinesis `Data=` which requires bytes.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def to_json_str(obj: Any) -> str:
    """
    Convert an object to a compact JSON string.
    - Use for SQS MessageBody which requires a string.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)




##############################



import logging
from utils.helpers import extract_payloads, to_json_bytes, to_json_str

logger = logging.getLogger(__name__)

def lambda_handler(event, context):
    records = [(r["messageId"], r["body"]) for r in event["Records"]]
    flattened_payloads = extract_payloads(records)

    # Kinesis: bytes
    for msg_id, payload in flattened_payloads:
        kinesis.put_record(
            StreamARN=kinesis_stream_name,
            Data=to_json_bytes(payload),
            PartitionKey=msg_id,
        )

    # SQS: strings
    msg_bodies = [to_json_str(payload) for _, payload in flattened_payloads]
    push_batch_to_sqs_concurrently(sqs, queue_url, msg_bodies)

    return {"ok": True, "count": len(flattened_payloads)}



#################


import json
import unittest
from utils.helpers import extract_payloads, to_json_bytes, to_json_str

class TestExtractPayloads(unittest.TestCase):
    # … existing tests …

    def test_to_json_bytes_and_str(self):
        # ensures serializers return the correct types and round-trip
        obj = {"k": 1, "s": "á"}
        s = to_json_str(obj)
        b = to_json_bytes(obj)
        self.assertIsInstance(s, str)
        self.assertIsInstance(b, (bytes, bytearray))
        self.assertEqual(json.loads(s), obj)
        self.assertEqual(json.loads(b.decode("utf-8")), obj)

if __name__ == "__main__":
    unittest.main()


