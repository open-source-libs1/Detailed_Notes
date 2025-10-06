
import json
import logging
from typing import Any, List, Sequence, Tuple

# Use your Lambda's configured logger; default to module logger.
logger = logging.getLogger(__name__)

# Public type aliases for clarity
MsgTuple = Tuple[str, Any]   # (messageId, payload_dict)
InTuple  = Tuple[str, str]   # (messageId, body_json_string)


def extract_payloads(records: Sequence[InTuple]) -> List[MsgTuple]:
    """
    Extract payload objects from SQS 'body' JSONs.

    What it does:
      - For each (messageId, body_json_string), parse `body_json_string` (outer JSON).
      - Expect `body` to contain: {"records": [{"payload": "<json-string or object>"} ...]}
      - Parse each inner `payload` (usually a JSON string in your logs).
      - Return a flat list of (messageId, payload_object) for all payloads found.

    Inputs:
      records: Sequence[Tuple[str, str]]
        A list (or any sequence) of (messageId, body_json_string) pairs.

    Returns:
      List[Tuple[str, Any]]
        Flat list of (messageId, payload_object). Bad items are skipped, not raised.

    Example:
      records = [
        ("db298357-...b423",
         '{ "version":2, "records":[{"payload":"{\\"k\\":1}"},{"payload":"{\\"k\\":2}"}] }')
      ]
      -> extract_payloads(records)
      [
        ("db298357-...b423", {"k": 1}),
        ("db298357-...b423", {"k": 2}),
      ]
    """
    out: List[MsgTuple] = []

    if not isinstance(records, (list, tuple)):
        # Keep it simple: we only expect a concrete list/tuple from the handler.
        logger.warning("helpers.extract_payloads: 'records' is not a list/tuple (got %s)", type(records).__name__)
        return out

    logger.debug("helpers.extract_payloads: starting with %d record(s)", len(records))

    for idx, (message_id, body_str) in enumerate(records):
        # Guard outer tuple types to avoid odd crashes
        if not isinstance(message_id, str) or not isinstance(body_str, str):
            logger.warning("Record %d: expected (str, str), got types (%s, %s); skipping",
                           idx, type(message_id).__name__, type(body_str).__name__)
            continue

        try:
            # Decode the outer body JSON once
            body = json.loads(body_str)
        except (TypeError, ValueError) as e:
            logger.warning("Record %d (id=%s): body is not valid JSON; skipping (%s)", idx, message_id, e)
            continue

        # Fetch the 'records' array; if not a list, we can't proceed
        inner = body.get("records")
        if not isinstance(inner, list):
            logger.warning("Record %d (id=%s): 'records' missing or not a list; skipping", idx, message_id)
            continue

        logger.debug("Record %d (id=%s): found %d inner record(s)", idx, message_id, len(inner))

        for j, rec in enumerate(inner):
            # Each rec should be a dict with a 'payload' key
            if not isinstance(rec, dict) or "payload" not in rec:
                logger.warning("Record %d (id=%s) inner %d: missing/invalid 'payload'; skipping", idx, message_id, j)
                continue

            raw = rec["payload"]

            try:
                # In your logs, payload is a JSON STRING; decode if string, else accept as-is
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError) as e:
                logger.warning("Record %d (id=%s) inner %d: payload not valid JSON; skipping (%s)",
                               idx, message_id, j, e)
                continue

            # Append the normalized result
            out.append((message_id, payload))

    logger.debug("helpers.extract_payloads: extracted %d payload(s) total", len(out))
    return out




#############


import json
import logging
import unittest

from helpers import extract_payloads

# Ensure logger emits during tests (helps cover logging branches)
logging.basicConfig(level=logging.DEBUG)


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
        # Sometimes payload may already be an object; ensure we accept it without json.loads
        p = {"hello": "world"}
        body = {"records": [{"payload": p}]}
        got = extract_payloads([("m3", json.dumps(body))])
        self.assertEqual(got, [("m3", p)])

    def test_invalid_body_json(self):
        # Bad JSON body -> skipped, no exception
        bad_body = "{not-json"
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m4", bad_body)])
        self.assertEqual(got, [])
        self.assertTrue(any("body is not valid JSON" in msg for msg in log.output[0:]))

    def test_records_not_list(self):
        # 'records' missing or not list -> skipped
        body = {"records": "not-a-list"}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m5", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("'records' missing or not a list" in msg for msg in log.output[0:]))

    def test_missing_payload_key(self):
        body = {"records": [{}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m6", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("missing/invalid 'payload'" in msg for msg in log.output[0:]))

    def test_payload_invalid_json_string(self):
        # payload exists but is an invalid JSON string -> skipped inner only
        body = {"records": [{"payload": "{bad-json"}]}
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([("m7", json.dumps(body))])
        self.assertEqual(got, [])
        self.assertTrue(any("payload not valid JSON" in msg for msg in log.output[0:]))

    def test_non_string_tuple_members(self):
        # Guard against wrong tuple types; should skip gracefully
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads([(123, {"not": "a string"})])  # wrong types
        self.assertEqual(got, [])
        self.assertTrue(any("expected (str, str)" in msg for msg in log.output[0:]))

    def test_non_sequence_input(self):
        # If someone passes a non-sequence by mistake
        with self.assertLogs(level="WARNING") as log:
            got = extract_payloads(None)  # type: ignore[arg-type]
        self.assertEqual(got, [])
        self.assertTrue(any("'records' is not a list/tuple" in msg for msg in log.output[0:]))

    def test_mixed_good_and_bad_inners(self):
        # Ensure good inner payloads are kept even if some are bad
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


if __name__ == "__main__":
    unittest.main()


