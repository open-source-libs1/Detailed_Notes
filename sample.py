from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Tuple

logger = logging.getLogger(__name__)


def explode_sqs_event_to_payloads(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Expands an SQS event (Event-2 shape) into (messageId, payload_json) tuples.

    Explanation:
        Each SQS record has a `body` JSON string which decodes to a dict that
        contains a `records` list. Each item in `records` includes a `payload`
        that is usually a JSON *string* (with escaped quotes like `\\\"`).
        This function decodes both layers and returns each payload as a compact
        JSON string, paired with the outer `messageId`.

        Non-conforming or undecodable records/payloads are skipped with a log.

    Args:
        event: The Lambda SQS event dict. Expected to contain a `Records` list.

    Returns:
        List of (message_id, payload_json_string) tuples.

    Example:
        >>> import json
        >>> body = {"records":[{"payload": json.dumps({"id":1})},
        ...                    {"payload": json.dumps({"id":2})}]}
        >>> event = {"Records":[{"messageId":"A","body": json.dumps(body)}]}
        >>> explode_sqs_event_to_payloads(event)
        [('A', '{"id":1}'), ('A', '{"id":2}')]
    """
    out: List[Tuple[str, str]] = []

    for rec in _iter_records(event):
        msg_id = rec.get("messageId") or rec.get("messageid")
        if not msg_id:
            logger.warning("Skipping record without messageId: %r", rec)
            continue

        body_obj = _decode_body_event2(rec.get("body"))
        if not isinstance(body_obj, dict):
            logger.warning("Skipping message %s: body could not be decoded to dict.", msg_id)
            continue

        for payload_json in _iter_payloads_event2(body_obj):
            out.append((msg_id, payload_json))

    return out


def _iter_records(event: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Safely yields dict records from `event['Records']`.

    Explanation:
        The event may not contain `Records`, or it may contain non-dict items.
        This helper yields only dict records to keep the main code clean.

    Args:
        event: The Lambda SQS event dict.

    Returns:
        An iterator of dict records (others are ignored).

    Example:
        >>> list(_iter_records({"Records":[{"messageId":"x"},"bad",None]}))
        [{'messageId': 'x'}]
    """
    records = event.get("Records")
    if isinstance(records, list):
        for r in records:
            if isinstance(r, dict):
                yield r


def _decode_body_event2(body: Any) -> Any:
    """Decode the record `body` for Event-2.

    Explanation:
        Event-2 bodies are typically:
          * a JSON string (most common), or
          * bytes/bytearray containing that JSON string, or
          * already a dict (in tests or upstream transforms).
        We parse with `strict=False` to tolerate control characters/newlines
        inside JSON strings (common when bodies include `\\n`).

    Args:
        body: Raw record body (str | bytes | bytearray | dict | other).

    Returns:
        Decoded Python object (usually a dict). Returns `None` on failure.

    Example:
        >>> import json
        >>> _decode_body_event2(json.dumps({"records": []}))
        {'records': []}
    """
    if body is None:
        return None

    if isinstance(body, (bytes, bytearray)):
        try:
            body = body.decode("utf-8")
        except Exception as e:
            logger.error("Failed to decode body bytes: %s", e)
            return None

    if isinstance(body, str):
        try:
            return json.loads(body, strict=False)
        except Exception as e:
            logger.error("Failed to parse body: %s", e)
            return None

    if isinstance(body, dict):
        return body

    # Any other type (int, float, etc.) is unsupported for Event-2
    logger.warning("Unsupported body type for Event-2: %r", type(body))
    return None


def _iter_payloads_event2(body_obj: Dict[str, Any]) -> Iterable[str]:
    """Yields compact JSON strings for each payload in `body_obj['records']`.

    Explanation:
        We expect `body_obj` to contain a `records` list. Each item must have
        a `payload`. If payload is:
          * a JSON string: we `json.loads(..., strict=False)` and re-dump compactly.
          * a dict/list: we dump it compactly as-is.
          * any other type: we skip it.

    Args:
        body_obj: The decoded body dict.

    Returns:
        An iterator of compact JSON strings, one per payload.

    Example:
        >>> import json
        >>> body = {"records":[
        ...   {"payload": json.dumps({"a":1})},
        ...   {"payload": {"b":2}},
        ... ]}
        >>> list(_iter_payloads_event2(body))
        ['{"a":1}', '{"b":2}']
    """
    records = body_obj.get("records")
    if not isinstance(records, list):
        logger.warning("Ignoring body without list 'records': %r", type(records))
        return

    for item in records:
        if not isinstance(item, dict) or "payload" not in item:
            logger.warning("Skipping non-dict or missing-payload item: %r", item)
            continue

        payload = item["payload"]

        # Most common: payload is a JSON string (with escaped quotes/newlines).
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload, strict=False)
            except Exception as e:
                logger.error("Failed to parse payload string: %s", e)
                continue
            yield json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
            continue

        # Already a JSON object/array.
        if isinstance(payload, (dict, list)):
            yield json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            continue

        # Unsupported type.
        logger.warning("Ignoring unsupported payload type: %r", type(payload))



########################



import json
import unittest

from src.utils.helpers import (
    explode_sqs_event_to_payloads,
    _iter_records,
    _decode_body_event2,
    _iter_payloads_event2,
)


class TestHelpersEvent2Only(unittest.TestCase):
    # ---------- explode_sqs_event_to_payloads (public) ----------

    def test_explode_multiple_payloads_single_record(self):
        payload1 = {"id": 1, "x": "a"}
        payload2 = {"id": 2, "x": "b"}
        body = {"records": [
            {"payload": json.dumps(payload1)},
            {"payload": json.dumps(payload2)}
        ]}
        event = {"Records": [{"messageId": "MID", "body": json.dumps(body)}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [
            ("MID", '{"id":1,"x":"a"}'),
            ("MID", '{"id":2,"x":"b"}'),
        ])

    def test_explode_handles_double_escaped_with_newlines(self):
        # Payload contains a newline and is double-escaped by outer json.dumps(body)
        payload = {"account_key": "test_tban", "is_enrollment_active": True, "note": "line1\nline2"}
        body = {"records": [{"payload": json.dumps(payload)}]}
        event = {"Records": [{"messageId": "A", "body": json.dumps(body)}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("A", '{"account_key":"test_tban","is_enrollment_active":true,"note":"line1\\nline2"}')])

    def test_explode_bytes_and_bytearray_bodies(self):
        body = {"records": [{"payload": json.dumps({"k": 7})}]}
        e_bytes = {"Records": [{"messageId": "B", "body": json.dumps(body).encode("utf-8")}]}
        e_barr  = {"Records": [{"messageId": "C", "body": bytearray(json.dumps(body).encode("utf-8"))}]}
        self.assertEqual(explode_sqs_event_to_payloads(e_bytes), [("B", '{"k":7}')])
        self.assertEqual(explode_sqs_event_to_payloads(e_barr),  [("C", '{"k":7}')])

    def test_explode_skips_missing_messageid_and_bad_body(self):
        # Missing messageId -> skipped
        body_ok = {"records": [{"payload": json.dumps({"z": 1})}]}
        # Invalid JSON string body -> skipped
        bad_body = "{invalid-json}"
        # Unsupported body type (int) -> skipped
        bad_type = 123

        event = {
            "Records": [
                {"body": json.dumps(body_ok)},  # no messageId
                {"messageId": "X", "body": bad_body},
                {"messageId": "Y", "body": bad_type},
                {"messageid": "lower", "body": json.dumps(body_ok)},  # supports lowercase key too
            ]
        }
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("lower", '{"z":1}')])

    def test_explode_no_records_or_empty(self):
        self.assertEqual(explode_sqs_event_to_payloads({"Records": []}), [])
        self.assertEqual(explode_sqs_event_to_payloads({}), [])


    # ---------- _iter_records ----------

    def test_iter_records_filters_non_dict(self):
        event = {"Records": [{"messageId": "a"}, "bad", None]}
        recs = list(_iter_records(event))
        self.assertEqual(recs, [{"messageId": "a"}])

    def test_iter_records_missing_key(self):
        self.assertEqual(list(_iter_records({})), [])


    # ---------- _decode_body_event2 ----------

    def test_decode_body_event2_variants(self):
        # valid str
        self.assertEqual(_decode_body_event2(json.dumps({"records": []})), {"records": []})
        # valid dict
        sentinel = {"records": [{"payload": "x"}]}
        self.assertIs(_decode_body_event2(sentinel), sentinel)
        # valid bytes
        self.assertEqual(_decode_body_event2(json.dumps({"a": 1}).encode()), {"a": 1})
        # invalid bytes (bad utf-8) -> None
        self.assertIsNone(_decode_body_event2(b"\xff\xfe\xfa"))
        # invalid JSON str -> None
        self.assertIsNone(_decode_body_event2("{invalid}"))
        # unsupported type -> None
        self.assertIsNone(_decode_body_event2(123))


    # ---------- _iter_payloads_event2 ----------

    def test_iter_payloads_event2_variants(self):
        # records not a list -> nothing
        self.assertEqual(list(_iter_payloads_event2({"records": "oops"})), [])

        body = {
            "records": [
                {"no_payload": 1},                       # missing payload -> skip
                {"payload": "not json"},                 # invalid payload string -> skip
                {"payload": json.dumps([1, 2, 3])},      # payload string (array) -> ok
                {"payload": {"k": 9}},                   # payload dict -> ok
                {"payload": [True, False]},              # payload list -> ok
                {"payload": 123},                        # unsupported type -> skip
            ]
        }
        out = list(_iter_payloads_event2(body))
        self.assertEqual(out, ['[1,2,3]', '{"k":9}', '[true,false]'])


if __name__ == "__main__":
    unittest.main()
