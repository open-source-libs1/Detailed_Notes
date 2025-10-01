# helpers.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Tuple, Union

logger = logging.getLogger(__name__)

Jsonable = Union[dict, list, str, int, float, bool, None]


def explode_sqs_event_to_payloads(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Expands an SQS event into a flat list of **(messageId, payload_json)** pairs.

    Each outer SQS Record can contain multiple inner payloads inside its `body`.
    This function extracts only the payloads and preserves their outer `messageId`
    for partial-failure reporting.

    Args:
        event: The full Lambda event payload containing `Records`.

    Returns:
        A list of (source_message_id, payload_json_string) tuples.

    Example:
        >>> event = {
        ...   "Records": [
        ...     {"messageId": "A", "body": {"records": [{"payload": {"id": 1}}, {"payload": {"id": 2}}]}},
        ...     {"messageId": "B", "body": '{"records":[{"payload":{"id":3}}]}'}
        ...   ]
        ... }
        >>> explode_sqs_event_to_payloads(event)
        [('A', '{"id":1}'), ('A', '{"id":2}'), ('B', '{"id":3}')]
    """
    results: List[Tuple[str, str]] = []

    for rec in event.get("Records", []):
        msg_id = rec.get("messageId") or rec.get("messageid")  # defensive
        if not msg_id:
            logger.debug("Skipping record without messageId: %r", rec)
            continue

        body_raw = rec.get("body")
        if body_raw is None:
            logger.debug("Skipping record with no body (messageId=%s)", msg_id)
            continue

        body_obj = _loads_multipass(body_raw)

        # Typical shape from your examples:
        # {"version":"...","batchMeta":{...},"records":[[{"meta":{...},"payload":"<json>"}]]}
        if isinstance(body_obj, dict) and "records" in body_obj:
            for inner in _flatten_records(body_obj["records"]):
                if not isinstance(inner, dict):
                    continue
                if "payload" not in inner:
                    continue
                payload_raw = inner["payload"]
                payload_obj = _loads_multipass(payload_raw)
                payload_str = _to_json_string(payload_obj)
                results.append((msg_id, payload_str))
            continue

        # Fallbacks: be liberal but deterministic
        if isinstance(body_obj, dict) and "payload" in body_obj:
            payload_obj = _loads_multipass(body_obj["payload"])
            results.append((msg_id, _to_json_string(payload_obj)))
            continue

        if isinstance(body_obj, dict):
            # Treat entire body as the payload if it looks like a self-contained request
            results.append((msg_id, _to_json_string(body_obj)))
            continue

        if isinstance(body_obj, str) and _looks_like_json(body_obj):
            payload_obj = _loads_multipass(body_obj)
            results.append((msg_id, _to_json_string(payload_obj)))
            continue

        logger.debug("Unrecognized body shape for messageId=%s: %r", msg_id, type(body_obj))

    return results


# -------------------------- internals -------------------------- #

def _loads_multipass(value: Any, *, max_passes: int = 4) -> Jsonable:
    """Robustly decode JSON across multiple escaping layers (\\, \\n, etc.).

    Behavior:
      * bytes/bytearray -> UTF-8 string
      * If already dict/list -> returned as-is
      * While it's a string that looks like JSON, keep json.loads() up to `max_passes`
      * Handles the common "JSON string of JSON string" pattern from SQS logs
    """
    cur: Any = value

    # Normalize bytes -> str
    if isinstance(cur, (bytes, bytearray)):
        cur = cur.decode("utf-8", errors="replace")

    # Fast exit
    if isinstance(cur, (dict, list)):
        return cur

    for _ in range(max_passes):
        if isinstance(cur, (dict, list)):
            return cur
        if not isinstance(cur, str):
            return cur

        s = cur.strip()

        try:
            decoded = json.loads(s, strict=False)
        except json.JSONDecodeError:
            # Sometimes the string is quoted JSON with visible escapes; try gentle unquote.
            if s and s[0] == s[-1] == '"':
                try:
                    decoded = json.loads(s[1:-1], strict=False)
                except Exception:
                    return cur
            else:
                return cur

        # If we decoded to a string that still looks like JSON, loop again.
        if isinstance(decoded, str) and _looks_like_json(decoded):
            cur = decoded
            continue

        return decoded

    return cur


def _flatten_records(records_field: Any) -> Iterator[dict]:
    """Yield dict items from 'records' which may be a list or a list-of-lists."""
    if isinstance(records_field, list):
        for item in records_field:
            if isinstance(item, list):
                for inner in item:
                    if isinstance(inner, dict):
                        yield inner
            elif isinstance(item, dict):
                yield item


def _looks_like_json(s: str) -> bool:
    s = s.lstrip()
    return s.startswith("{") or s.startswith("[")


def _to_json_string(obj: Jsonable) -> str:
    """Normalize any JSON-able object to a compact JSON string."""
    if isinstance(obj, str) and _looks_like_json(obj):
        return obj
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)




###############################


# test_helpers.py
import json
import unittest

from helpers import explode_sqs_event_to_payloads, _loads_multipass, _to_json_string


class TestExplodeSQSEvent(unittest.TestCase):
    def test_multiple_payloads_per_record_dict_body(self):
        event = {
            "Records": [
                {
                    "messageId": "A",
                    "body": {
                        "version": "1",
                        "records": [
                            {"payload": {"id": 1}},
                            {"payload": {"id": 2}},
                        ],
                    },
                }
            ]
        }
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("A", '{"id":1}'), ("A", '{"id":2}')])

    def test_multiple_records_and_stringified_body(self):
        body = json.dumps({"records": [{"payload": {"id": 3}}]})
        event = {
            "Records": [
                {"messageId": "A", "body": body},
                {"messageId": "B", "body": body},
            ]
        }
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(
            out,
            [("A", '{"id":3}'), ("B", '{"id":3}')],
        )

    def test_list_of_lists_records_and_escaped_payload_string(self):
        # Simulate the heavy-escaped payload you see in logs:
        inner_payload = {"meta": {"ref": "x"}, "payload": {"k": "v", "n": 1}}
        container = {"version": "2", "records": [[inner_payload, inner_payload]]}
        # Encode twice to create visible backslashes/newlines in a log
        once = json.dumps(container)
        twice = json.dumps(once)  # string of a string
        event = {"Records": [{"messageId": "X", "body": twice}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(
            out,
            [("X", '{"k":"v","n":1}'), ("X", '{"k":"v","n":1}')],
        )

    def test_body_with_direct_payload_field(self):
        event = {
            "Records": [
                {"messageId": "Z", "body": {"payload": {"x": 10}}},
            ]
        }
        self.assertEqual(explode_sqs_event_to_payloads(event), [("Z", '{"x":10}')])

    def test_body_dict_without_records_or_payload_treated_as_payload(self):
        event = {"Records": [{"messageId": "Q", "body": {"x": 1, "y": 2}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("Q", '{"x":1,"y":2}')])

    def test_body_is_json_string_payload_object(self):
        body = '{"id":42,"ok":true}'
        event = {"Records": [{"messageId": "S", "body": body}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("S", body)])

    def test_bytes_and_bytearray_inputs(self):
        container = {"records": [{"payload": {"b": 1}}, {"payload": {"b": 2}}]}
        body_bytes = json.dumps(container).encode("utf-8")
        event = {"Records": [{"messageId": "B1", "body": body_bytes}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("B1", '{"b":1}'), ("B1", '{"b":2}')])

        # payload embedded as bytes inside body dict
        event2 = {"Records": [{"messageId": "B2", "body": {"payload": body_bytes}}]}
        out2 = explode_sqs_event_to_payloads(event2)
        self.assertEqual(out2, [("B2", '{"b":1,"b":2}'.replace('"b":1,"b":2"', '"b":1,"b":2"'))])  # sanity

    def test_missing_message_id_is_skipped(self):
        event = {"Records": [{"body": {"payload": {"x": 1}}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_missing_body_is_skipped(self):
        event = {"Records": [{"messageId": "M"}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_unrecognized_body_shape_is_ignored(self):
        event = {"Records": [{"messageId": "U", "body": 12345}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_empty_records(self):
        self.assertEqual(explode_sqs_event_to_payloads({"Records": []}), [])

    # ---- internal helpers coverage ----

    def test_loads_multipass_string_of_string(self):
        obj = {"a": 1}
        s1 = json.dumps(obj)
        s2 = json.dumps(s1)        # string-of-string (double-escaped)
        decoded = _loads_multipass(s2)
        self.assertEqual(decoded, obj)

    def test_loads_multipass_non_json_string_returns_original(self):
        self.assertEqual(_loads_multipass("not json"), "not json")

    def test_to_json_string_passes_through_compact(self):
        self.assertEqual(_to_json_string({"a": 1, "b": 2}), '{"a":1,"b":2}')
        already = '{"x":3}'
        self.assertEqual(_to_json_string(already), already)


if __name__ == "__main__":
    unittest.main()
