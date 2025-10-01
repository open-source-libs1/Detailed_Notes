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
        ...     {"messageId": "A",
        ...      "body": {"records":[{"payload":{"id":1}}, {"payload":{"id":2}}]}},
        ...     {"messageId": "B",
        ...      "body": '{"records":[{"payload":{"id":3}}]}'}
        ...   ]
        ... }
        >>> explode_sqs_event_to_payloads(event)
        [('A', '{"id":1}'), ('A', '{"id":2}'), ('B', '{"id":3}')]
    """
    results: List[Tuple[str, str]] = []

    for rec in (event.get("Records") or []):
        msg_id = rec.get("messageId") or rec.get("messageid")
        if not msg_id:
            logger.debug("Skipping record without messageId: %r", rec)
            continue

        body_raw = rec.get("body")
        if body_raw is None:
            logger.debug("Skipping record with no body (messageId=%s)", msg_id)
            continue

        body_obj = _loads_multipass(body_raw)

        # 1) Preferred path: top-level 'records'
        found = False
        if isinstance(body_obj, dict) and "records" in body_obj:
            recs = body_obj["records"]
            if not isinstance(recs, (list, dict)):
                recs = _loads_multipass(recs)
            for inner in _flatten_records(recs):
                if isinstance(inner, dict) and "payload" in inner:
                    payload_obj = _loads_multipass(inner["payload"])
                    results.append((msg_id, _to_json_string(payload_obj)))
                    found = True
        if found:
            continue  # we extracted at least one payload from 'records'

        # 2) Single 'payload' at top-level, which might itself contain 'records'
        if isinstance(body_obj, dict) and "payload" in body_obj:
            payload_obj = _loads_multipass(body_obj["payload"])
            if isinstance(payload_obj, dict) and "records" in payload_obj:
                recs2 = payload_obj["records"]
                if not isinstance(recs2, (list, dict)):
                    recs2 = _loads_multipass(recs2)
                for inner in _flatten_records(recs2):
                    if isinstance(inner, dict) and "payload" in inner:
                        inner_payload = _loads_multipass(inner["payload"])
                        results.append((msg_id, _to_json_string(inner_payload)))
                if results:
                    continue
            # Otherwise treat payload as the final message
            results.append((msg_id, _to_json_string(payload_obj)))
            continue

        # 3) Body is a dict but with no 'records'/'payload' -> treat body as the payload
        if isinstance(body_obj, dict):
            results.append((msg_id, _to_json_string(body_obj)))
            continue

        # 4) Body is a JSON-looking string — peel & normalize
        if isinstance(body_obj, str) and _looks_like_json(body_obj):
            payload_obj = _loads_multipass(body_obj)
            # If after peeling we find 'records', extract multiple payloads
            if isinstance(payload_obj, dict) and "records" in payload_obj:
                recs3 = payload_obj["records"]
                if not isinstance(recs3, (list, dict)):
                    recs3 = _loads_multipass(recs3)
                extracted_any = False
                for inner in _flatten_records(recs3):
                    if isinstance(inner, dict) and "payload" in inner:
                        inner_payload = _loads_multipass(inner["payload"])
                        results.append((msg_id, _to_json_string(inner_payload)))
                        extracted_any = True
                if extracted_any:
                    continue
            results.append((msg_id, _to_json_string(payload_obj)))
            continue

        logger.debug("Unrecognized body shape for messageId=%s: %r", msg_id, type(body_obj))

    return results


# -------------------------- internals -------------------------- #

def _loads_multipass(value: Any, *, max_passes: int = 8) -> Jsonable:
    """Robustly decode JSON across multiple escaping layers (\\\\, \\n, etc.).

    Strategy:
      * bytes/bytearray -> UTF-8 string
      * While value is a string:
         1) Try json.loads()
         2) If that fails and string is quoted, strip ONE outer quote layer and retry
         3) If that fails and string contains backslashes, apply unicode-escape and retry
         4) If still not JSON, stop and return the string as-is
      * Repeat up to `max_passes` to peel double/triple encodings.
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

        # Try plain JSON
        try:
            decoded = json.loads(s, strict=False)
            # If decoded into a JSON string that itself looks like JSON, keep peeling
            if isinstance(decoded, str) and _looks_like_json(decoded.strip()):
                cur = decoded
                continue
            return decoded
        except json.JSONDecodeError:
            pass  # proceed to transformations

        transformed = False

        # Strip a single layer of surrounding quotes if present
        if s and s[0] == s[-1] == '"':
            s = s[1:-1]
            transformed = True

        # Attempt unicode escape (handles \\n, \\" showing up literally)
        if "\\" in s:
            try:
                s2 = bytes(s, "utf-8").decode("unicode_escape")
                s = s2
                transformed = True
            except Exception:
                # If unicode_escape fails, keep the original s
                pass

        if not transformed:
            # No progress can be made
            return cur

        cur = s  # loop again with the transformed candidate

    return cur


def _flatten_records(records_field: Any) -> Iterator[dict]:
    """Yield dict items from `records`, tolerating list, list-of-lists, or deeper nesting."""
    def _walk(obj: Any) -> Iterator[dict]:
        if isinstance(obj, dict):
            yield obj
        elif isinstance(obj, list):
            for item in obj:
                yield from _walk(item)
        else:
            # If 'records' itself is a JSON string, try to peel it once more.
            if isinstance(obj, str) and _looks_like_json(obj):
                peeled = _loads_multipass(obj)
                yield from _walk(peeled)

    yield from _walk(records_field)


def _looks_like_json(s: str) -> bool:
    s = s.lstrip()
    return s.startswith("{") or s.startswith("[")


def _to_json_string(obj: Jsonable) -> str:
    """Normalize any JSON-able object to a compact JSON string."""
    if isinstance(obj, str) and _looks_like_json(obj.strip()):
        return obj
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)




##################################################



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
        self.assertEqual(out, [("A", '{"id":3}'), ("B", '{"id":3}')])

    def test_list_of_lists_records_and_double_escaped_string(self):
        # Build a container with two equal payloads
        inner_payload = {"meta": {"ref": "x"}, "payload": {"k": "v", "n": 1}}
        container = {"version": "2", "records": [[inner_payload, inner_payload]]}
        # Encode twice to simulate CloudWatch style double-escaping (string-of-string)
        once = json.dumps(container)
        twice = json.dumps(once)
        event = {"Records": [{"messageId": "X", "body": twice}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("X", '{"k":"v","n":1}'), ("X", '{"k":"v","n":1}')])

    def test_records_field_is_string_needing_extra_peel(self):
        recs = json.dumps([{"payload": {"a": 1}}, {"payload": {"a": 2}}])
        event = {"Records": [{"messageId": "R", "body": {"records": recs}}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("R", '{"a":1}'), ("R", '{"a":2}')])

    def test_payload_contains_records_after_peel(self):
        # body is dict -> payload is string that decodes to container->records
        inner = {"records": [{"payload": {"p": 1}}, {"payload": {"p": 2}}]}
        payload_str = json.dumps(inner)
        event = {"Records": [{"messageId": "Y", "body": {"payload": payload_str}}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("Y", '{"p":1}'), ("Y", '{"p":2}')])

    def test_body_with_direct_payload_field(self):
        event = {"Records": [{"messageId": "Z", "body": {"payload": {"x": 10}}}]}
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

        # case 1: body is bytes representing the container
        event = {"Records": [{"messageId": "B1", "body": body_bytes}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("B1", '{"b":1}'), ("B1", '{"b":2}')])

        # case 2: body is a dict with payload=bytes(container)
        event2 = {"Records": [{"messageId": "B2", "body": {"payload": body_bytes}}]}
        out2 = explode_sqs_event_to_payloads(event2)
        self.assertEqual(out2, [("B2", '{"b":1}'), ("B2", '{"b":2}')])

        # case 3: same as case 1 but using bytearray
        event3 = {"Records": [{"messageId": "B3", "body": bytearray(body_bytes)}]}
        out3 = explode_sqs_event_to_payloads(event3)
        self.assertEqual(out3, [("B3", '{"b":1}'), ("B3", '{"b":2}')])

    def test_double_escaped_newlines_and_quotes(self):
        # Simulate CloudWatch-like string that shows \n and \"
        raw = '{\\n  \\"records\\": [{\\n    \\"payload\\": {\\n      \\"t\\": 1\\n    }\\n  }, {\\n    \\"payload\\": {\\n      \\"t\\": 2\\n    }\\n  }]\\n}'
        event = {"Records": [{"messageId": "N", "body": raw}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("N", '{"t":1}'), ("N", '{"t":2}')])

    def test_missing_message_id_is_skipped(self):
        event = {"Records": [{"body": {"payload": {"x": 1}}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_missing_body_is_skipped(self):
        event = {"Records": [{"messageId": "M"}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_unrecognized_body_shape_is_ignored(self):
        event = {"Records": [{"messageId": "U", "body": 12345}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_empty_records_and_no_records_key(self):
        self.assertEqual(explode_sqs_event_to_payloads({"Records": []}), [])
        self.assertEqual(explode_sqs_event_to_payloads({}), [])

    # ---- internal helper coverage ----

    def test_loads_multipass_string_of_string(self):
        obj = {"a": 1}
        s1 = json.dumps(obj)
        s2 = json.dumps(s1)  # double-encoded
        decoded = _loads_multipass(s2)
        self.assertEqual(decoded, obj)

    def test_loads_multipass_non_json_string_returns_original(self):
        self.assertEqual(_loads_multipass("not json"), "not json")

    def test_loads_multipass_gentle_unicode_unescape(self):
        raw = '{\\n  \\"a\\": 1\\n}'
        decoded = _loads_multipass(raw)
        self.assertEqual(decoded, {"a": 1})

    def test_to_json_string_compact_and_passthrough(self):
        self.assertEqual(_to_json_string({"a": 1, "b": 2}), '{"a":1,"b":2}')
        already = '{"x":3}'
        self.assertEqual(_to_json_string(already), already)


if __name__ == "__main__":
    unittest.main()
