


import json
import logging
from typing import Any, List, Sequence, Tuple

# Keep logging simple: use the module logger; messages propagate to root.
logger = logging.getLogger(__name__)

# Public type aliases for clarity
MsgTuple = Tuple[str, Any]   # (messageId, payload_object)
InTuple  = Tuple[str, str]   # (messageId, body_json_string)

def extract_payloads(records: Sequence[InTuple]) -> List[MsgTuple]:
    """
    Extract payload objects from SQS 'body' JSONs.

    What it does
    ------------
    For each (messageId, body_json_string):
      1) json.loads(body_json_string)  -> a dict expected to contain "records".
      2) For each item in body["records"], read "payload".
      3) If payload is a JSON string (your logs), json.loads(payload). If it's already an
         object (dict/list), use it as-is.
      4) Return a flat list of (messageId, payload_object).

    Parameters
    ----------
    records : Sequence[Tuple[str, str]]
        The list/sequence you build in the handler: [(messageId, body_json_string), ...].

    Returns
    -------
    List[Tuple[str, Any]]
        [(messageId, payload_object), ...]. Malformed items are skipped with warnings.

    Example
    -------
    records = [
        ("db298357-...b423",
         '{ "version":2, "records":[{"payload":"{\\"k\\":1}"},{"payload":"{\\"k\\":2}"}] }')
    ]
    extract_payloads(records)
    # -> [("db298357-...b423", {"k": 1}), ("db298357-...b423", {"k": 2})]
    """
    out: List[MsgTuple] = []

    # We expect a list/tuple of (str, str). If not, warn and bail.
    if not isinstance(records, (list, tuple)):
        logger.warning("extract_payloads: 'records' is not a list/tuple (got %s)", type(records).__name__)
        return out

    logger.debug("extract_payloads: starting with %d record(s)", len(records))

    for idx, item in enumerate(records):
        # Defensive shape check before unpacking
        if (not isinstance(item, (list, tuple))) or len(item) != 2:
            logger.warning("Record %d: expected a 2-tuple, got %r; skipping", idx, item)
            continue

        message_id, body_str = item

        if not isinstance(message_id, str) or not isinstance(body_str, str):
            logger.warning("Record %d: expected (str, str), got (%s, %s); skipping",
                           idx, type(message_id).__name__, type(body_str).__name__)
            continue

        # 1) Decode the outer body JSON
        try:
            body = json.loads(body_str)
        except (TypeError, ValueError) as e:
            logger.warning("Record %d (id=%s): body is not valid JSON; skipping (%s)", idx, message_id, e)
            continue

        # 2) Get the inner "records" list
        inner = body.get("records")
        if not isinstance(inner, list):
            logger.warning("Record %d (id=%s): 'records' missing or not a list; skipping", idx, message_id)
            continue

        logger.debug("Record %d (id=%s): found %d inner record(s)", idx, message_id, len(inner))

        # 3) For each inner record, pull and decode 'payload'
        for j, rec in enumerate(inner):
            if not isinstance(rec, dict) or "payload" not in rec:
                logger.warning("Record %d (id=%s) inner %d: missing/invalid 'payload'; skipping", idx, message_id, j)
                continue

            raw = rec["payload"]
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError) as e:
                logger.warning("Record %d (id=%s) inner %d: payload not valid JSON; skipping (%s)",
                               idx, message_id, j, e)
                continue

            out.append((message_id, payload))

    logger.debug("extract_payloads: extracted %d payload(s) total", len(out))
    return out





########################



import json
import logging
import unittest

# Ensure logs appear during tests (use root capture in assertLogs()).
logging.basicConfig(level=logging.DEBUG)

from helpers import extract_payloads  # adjust import to your path if needed


class TestExtractPayloads(unittest.TestCase):
    def test_single_payload(self):
        payload = {"account_key": "A", "n": 1}
        body = {"version": 2, "records": [{"payload": json.dumps(payload)}]}
        records = [("m1", json.dumps(body))]
        got = extract_payloads(records)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "m1")
        self.assertEqual(got[0][1], payload)

    def test_multiple_payloads(self):
        p1 = {"k": 1}
        p2 = {"k": 2}
        body = {"version": 2, "records": [{"payload": json.dumps(p1)}, {"payload": json.dumps(p2)}]}
        records = [("m2", json.dumps(body))]
        got = extract_payloads(records)
        self.assertEqual([g[1]["k"] for g in got], [1, 2])
        self.assertTrue(all(g[0] == "m2" for g in got))

    def test_payload_is_already_object(self):
        p = {"hello": "world"}
        body = {"records": [{"payload": p}]}
        got = extract_payloads([("m3", json.dumps(body))])
        self.assertEqual(got, [("m3", p)])

    def test_invalid_body_json(self):
        bad_body = "{not-json"
        with self.assertLogs(level="WARNING") as log:  # capture ROOT; module logs propagate
            got = extract_payloads([("m4", bad_body)])
        self.assertEqual(got, [])
        self.assertTrue(any("body is not valid JSON" in msg for msg in log.output))

    def test_records_not_list(self):
        body = {"records": "not-a-list"}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m5", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("'records' missing or not a list" in msg for msg in log.output))

    def test_missing_payload_key(self):
        body = {"records": [{}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m6", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("missing/invalid 'payload'" in msg for msg in log.output))

    def test_payload_invalid_json_string(self):
        body = {"records": [{"payload": "{bad-json"}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m7", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("payload not valid JSON" in msg for msg in log.output))

    def test_non_string_tuple_members(self):
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([(123, {"not": "a string"})])  # wrong types
        self.assertEqual(got, [])
        self.assertTrue(any("expected (str, str)" in msg for msg in log.output))

    def test_non_sequence_input(self):
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads(None)  # type: ignore[arg-type]
        self.assertEqual(got, [])
        self.assertTrue(any("'records' is not a list/tuple" in msg for msg in log.output))

    def test_mixed_good_and_bad_inners(self):
        p_good = {"k": 9}
        body = {
            "records": [
                {"payload": "{bad-json"},          # bad
                {"payload": json.dumps(p_good)},   # good
                {},                                # missing
            ]
        }
        with self.assertLogs(level="WARNING"):
            got = extract_payloads([("m8", json.dumps(body))])
        self.assertEqual(got, [("m8", p_good)])



