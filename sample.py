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
      3) If `payload` is a JSON string (your logs), parse it; if it's already an object, use it.
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

    for idx, item in enumerate(records):
        # Unpack (by contract from handler: a 2-tuple of (str, str))
        message_id, body_str = item

        # Defensive type check (kept minimal per our simplification)
        if not isinstance(message_id, str) or not isinstance(body_str, str):
            logger.warning(
                "Record %d: expected (str, str), got (%s, %s); skipping",
                idx, type(message_id).__name__, type(body_str).__name__
            )
            continue

        # 1) Decode the outer body JSON
        try:
            body = json.loads(body_str)
        except (TypeError, ValueError) as e:
            logger.warning("Record %d (id=%s): body is not valid JSON; skipping (%s)", idx, message_id, e)
            continue

        # 2) Get the inner "records" list safely (None if missing)
        inner = body.get("records")  # safer than body["records"] to avoid KeyError
        if not isinstance(inner, list):
            logger.warning("Record %d (id=%s): 'records' missing or not a list; skipping", idx, message_id)
            continue

        logger.debug("Record %d (id=%s): found %d inner record(s)", idx, message_id, len(inner))

        # 3) Pull and decode each 'payload'
        for j, rec in enumerate(inner):
            if not isinstance(rec, dict) or "payload" not in rec:
                logger.warning("Record %d (id=%s) inner %d: missing/invalid 'payload'; skipping", idx, message_id, j)
                continue

            raw = rec["payload"]
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw  # JSON string → object
            except (TypeError, ValueError) as e:
                logger.warning(
                    "Record %d (id=%s) inner %d: payload not valid JSON; skipping (%s)",
                    idx, message_id, j, e
                )
                continue

            out.append((message_id, payload))

    logger.debug("extract_payloads: extracted %d payload(s) total", len(out))
    return out




###########


import json
import logging
import unittest

# Enable logging; tests capture ROOT via assertLogs()
logging.basicConfig(level=logging.DEBUG)

from helpers import extract_payloads


class TestExtractPayloads(unittest.TestCase):
    def test_single_payload(self):
        # Verifies we decode one payload string inside body.records
        payload = {"account_key": "A", "n": 1}
        body = {"version": 2, "records": [{"payload": json.dumps(payload)}]}
        records = [("m1", json.dumps(body))]
        got = extract_payloads(records)
        self.assertEqual(got, [("m1", payload)])

    def test_multiple_payloads(self):
        # Verifies multiple payloads in the same body are all returned
        p1, p2 = {"k": 1}, {"k": 2}
        body = {"version": 2, "records": [{"payload": json.dumps(p1)}, {"payload": json.dumps(p2)}]}
        got = extract_payloads([("m2", json.dumps(body))])
        self.assertEqual([x[1]["k"] for x in got], [1, 2])
        self.assertTrue(all(x[0] == "m2" for x in got))

    def test_payload_is_object(self):
        # Verifies payload already being an object is accepted without json.loads
        p = {"hello": "world"}
        body = {"records": [{"payload": p}]}
        got = extract_payloads([("m3", json.dumps(body))])
        self.assertEqual(got, [("m3", p)])

    def test_invalid_body_json(self):
        # Verifies invalid body JSON is skipped and warns
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m4", "{not-json")])
        self.assertEqual(got, [])
        self.assertTrue(any("body is not valid JSON" in s for s in log.output))

    def test_records_missing_or_not_list(self):
        # Verifies missing or non-list 'records' is skipped and warns
        body = {"records": "not-a-list"}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m5", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("'records' missing or not a list" in s for s in log.output))

    def test_missing_payload_key(self):
        # Verifies an inner record without 'payload' is skipped and warns
        body = {"records": [{}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m6", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("missing/invalid 'payload'" in s for s in log.output))

    def test_payload_invalid_json_string(self):
        # Verifies a bad payload JSON string is skipped and warns
        body = {"records": [{"payload": "{bad-json"}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m7", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("payload not valid JSON" in s for s in log.output))

    def test_non_string_tuple_members(self):
        # Verifies non-string (id, body) members are skipped and warn
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([(123, {"not": "a string"})])  # wrong types by design
        self.assertEqual(got, [])
        self.assertTrue(any("expected (str, str)" in s for s in log.output))

    def test_mixed_good_and_bad_inners(self):
        # Verifies good payloads are kept even when some inners are bad
        good = {"k": 9}
        body = {"records": [{"payload": "{bad-json"}, {"payload": json.dumps(good)}, {}]}
        with self.assertLogs(level="WARNING"):
            got = extract_payloads([("m8", json.dumps(body))])
        self.assertEqual(got, [("m8", good)])


if __name__ == "__main__":
    unittest.main()


