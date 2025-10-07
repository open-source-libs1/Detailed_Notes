

raw = rec["payload"]
if not isinstance(raw, str):
    logger.warning("Record (id=%s): payload is not string; skipping", message_id)
    continue

try:
    payload = json.loads(raw)



#######

# agreed. Payloads should always arrive as JSON strings, so passing non-string raw objects downstream doesn’t make sense.
# I’ve updated the logic to skip when payload is not a string and rely on the existing TypeError/ValueError handling for malformed JSON. This keeps behavior consistent and avoids sending invalid data to Kinesis.

#######


for message_id, body_str in records:
    ...
    logger.warning("Record (id=%s): ...", message_id, ...)




#######

# I’ve removed the index-based logging and now rely solely on messageId for log traceability.
# This keeps logs stable between Lambda invocations and makes them easier to correlate across retries or different batches.

#######


body_records = body.get("records")
for rec in body_records:



# ######

# Updated inner → body_records for clarity. This makes it easier to distinguish between the outer event records (from SQS) and the inner records field inside each message body.

######


logger.debug("Record (id=%s): found %d inner record(s)", message_id, len(body_records))

# 3) pull and decode each 'payload'
for rec in body_records:
    if not isinstance(rec, dict) or "payload" not in rec:
        logger.warning("Record (id=%s): missing/invalid 'payload'; skipping", message_id)
        continue


######

# removed the use of enumerate() and simplified the logging to rely solely on messageId for clarity.
# The index didn’t add much diagnostic value since it resets between runs, so we now consistently track all logs by messageId only.

######




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

    What it does
    ------------
    For each (messageId, body_json_string):
      1) Parse body_json_string (outer JSON).
      2) Expect `body["records"]` to be a list of objects with a `payload` field.
      3) `payload` must be a JSON string; parse it into an object.
      4) Return a flat list of (messageId, payload_object).

    Parameters
    ----------
    records : Sequence[Tuple[str, str]]
        Built in the handler as: [(r["messageId"], r["body"]) for r in event["Records"]].

    Returns
    -------
    List[Tuple[str, Any]]
        [(messageId, payload_object), ...] — malformed entries are skipped with warnings.

    Example
    -------
    records = [
        ("12345", '{ "version":2, "records":[{"payload":"{\\"k\\":1}"},{"payload":"{\\"k\\":2}"}] }')
    ]
    extract_payloads(records)
    # -> [("12345", {"k": 1}), ("12345", {"k": 2})]
    """
    out: List[MsgTuple] = []

    logger.debug("extract_payloads: starting with %d record(s)", len(records))

    # Iterate each SQS item: contract is (messageId, body_json_string)
    for message_id, body_str in records:
        # Minimal defensive check to avoid surprising crashes
        if not isinstance(message_id, str) or not isinstance(body_str, str):
            logger.warning(
                "Record (id=%s): expected (str, str), got (%s, %s); skipping",
                message_id, type(message_id).__name__, type(body_str).__name__
            )
            continue

        # 1) Decode the outer body JSON
        try:
            body = json.loads(body_str)
        except (TypeError, ValueError) as e:
            logger.warning("Record (id=%s): body is not valid JSON; skipping (%s)", message_id, e)
            continue

        # 2) Safely access inner list `records`
        body_records = body.get("records")  # None if missing
        if not isinstance(body_records, list):
            logger.warning("Record (id=%s): 'records' missing or not a list; skipping", message_id)
            continue

        logger.debug("Record (id=%s): found %d inner record(s)", message_id, len(body_records))

        # 3) Pull and decode each 'payload'
        for rec in body_records:
            if not isinstance(rec, dict) or "payload" not in rec:
                logger.warning("Record (id=%s): missing/invalid 'payload'; skipping", message_id)
                continue

            raw = rec["payload"]

            # Per contract: payload should be a JSON *string* (skip otherwise)
            if not isinstance(raw, str):
                logger.warning("Record (id=%s): payload is not a string; skipping", message_id)
                continue

            try:
                payload = json.loads(raw)  # JSON string → object
            except (TypeError, ValueError) as e:
                logger.warning("Record (id=%s): payload not valid JSON; skipping (%s)", message_id, e)
                continue

            out.append((message_id, payload))

    logger.debug("extract_payloads: extracted %d payload(s) total", len(out))
    return out



#################

import json
import logging
import unittest

# Enable logging; tests capture ROOT via assertLogs()
logging.basicConfig(level=logging.DEBUG)

from utils.helpers import extract_payloads


class TestExtractPayloads(unittest.TestCase):
    def test_single_payload(self):
        # Decodes one payload string inside body.records
        payload = {"account_key": "A", "n": 1}
        body = {"version": 2, "records": [{"payload": json.dumps(payload)}]}
        records = [("m1", json.dumps(body))]
        got = extract_payloads(records)
        self.assertEqual(got, [("m1", payload)])

    def test_multiple_payloads(self):
        # Returns all payloads from the same message body
        p1, p2 = {"k": 1}, {"k": 2}
        body = {"version": 2, "records": [{"payload": json.dumps(p1)}, {"payload": json.dumps(p2)}]}
        got = extract_payloads([("m2", json.dumps(body))])
        self.assertEqual([x[1]["k"] for x in got], [1, 2])
        self.assertTrue(all(x[0] == "m2" for x in got))

    def test_invalid_body_json(self):
        # Invalid outer JSON -> skip and warn
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m3", "{not-json")])
        self.assertEqual(got, [])
        self.assertTrue(any("body is not valid JSON" in s for s in log.output))

    def test_records_missing_or_not_list(self):
        # Missing or non-list 'records' -> skip and warn
        body = {"records": "not-a-list"}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m4", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("'records' missing or not a list" in s for s in log.output))

    def test_missing_payload_key(self):
        # Inner record without 'payload' -> skip and warn
        body = {"records": [{}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m5", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("missing/invalid 'payload'" in s for s in log.output))

    def test_payload_not_string(self):
        # Payload present but not a string -> skip and warn
        body = {"records": [{"payload": {"hello": "world"}}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m6", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("payload is not a string" in s for s in log.output))

    def test_payload_invalid_json_string(self):
        # Payload is a string but not valid JSON -> skip and warn
        body = {"records": [{"payload": "{bad-json"}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m7", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("payload not valid JSON" in s for s in log.output))

    def test_non_string_tuple_members(self):
        # (id, body) types are wrong -> skip and warn
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([(123, {"not": "a string"})])  # wrong types by design
        self.assertEqual(got, [])
        self.assertTrue(any("expected (str, str)" in s for s in log.output))

    def test_mixed_good_and_bad_inners(self):
        # Good payloads are retained even when some inners are bad
        good = {"k": 9}
        body = {
            "records": [
                {"payload": "{bad-json"},             # bad json string
                {"payload": json.dumps(good)},        # good
                {"payload": {"should": "skip"}},      # not string
                {},                                   # missing payload
            ]
        }
        with self.assertLogs(level="WARNING"):
            got = extract_payloads([("m8", json.dumps(body))])
        self.assertEqual(got, [("m8", good)])


if __name__ == "__main__":
    unittest.main()







