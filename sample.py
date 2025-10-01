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
            continue  # extracted at least one payload from 'records'

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

        # 4) Body is already a list (e.g., '["x", 1]') -> treat as payload
        if isinstance(body_obj, list):
            results.append((msg_id, _to_json_string(body_obj)))
            continue

        # 5) Body is a JSON-looking string — peel & normalize
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
            - If it yields a JSON string that itself *looks like* JSON, keep peeling
            - If it yields a plain string (not JSON-looking), **preserve the original**
         2) If that fails and string is quoted, strip ONE outer quote layer and retry
         3) If that fails and string contains backslashes, apply unicode-escape and retry
         4) If still not JSON, stop and return the (possibly transformed) string
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
            # If decoded to a string:
            if isinstance(decoded, str):
                # JSON string that *contains* JSON -> keep peeling
                if _looks_like_json(decoded.strip()):
                    cur = decoded
                    continue
                # Plain non-JSON string (e.g., "not json"): preserve **original** input
                return cur
            # Decoded to dict/list/number/bool/null -> done
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




###########################


# tests/utils/test_helpers.py
import json
import unittest

from src.utils.helpers import (
    explode_sqs_event_to_payloads,
    _loads_multipass,
    _flatten_records,
    _to_json_string,
)


class TestHelpersFullCoverage(unittest.TestCase):
    # ---------------------------------------------------------------------
    # explode_sqs_event_to_payloads — primary success paths
    # ---------------------------------------------------------------------

    def test_records_list_multiple_payloads(self):
        event = {
            "Records": [
                {
                    "messageId": "A",
                    "body": {
                        "records": [
                            {"payload": {"p": 1}},
                            {"payload": {"p": 2}},
                        ]
                    },
                }
            ]
        }
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("A", '{"p":1}'), ("A", '{"p":2}')],
        )

    def test_messageid_lowercase_records_is_dict(self):
        event = {"Records": [{"messageid": "x", "body": {"records": {"payload": {"x": 1}}}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("x", '{"x":1}')])

    def test_records_list_of_lists_and_inner_string(self):
        inner_list = json.dumps([{"payload": {"z": 9}}])
        event = {
            "Records": [
                {
                    "messageId": "deep",
                    "body": {"records": [[{"payload": {"z": 7}}], [[inner_list]]]},
                }
            ]
        }
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("deep", '{"z":7}'), ("deep", '{"z":9}')],
        )

    def test_payload_field_decodes_to_container_with_records(self):
        inner = {"records": [{"payload": {"q": 5}}, {"payload": {"q": 6}}]}
        event = {"Records": [{"messageId": "nested", "body": {"payload": json.dumps(inner), "noop": True}}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("nested", '{"q":5}'), ("nested", '{"q":6}')],
        )

    def test_payload_field_simple_dict(self):
        event = {"Records": [{"messageId": "simple", "body": {"payload": {"x": 10}}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("simple", '{"x":10}')])

    def test_body_dict_without_records_or_payload(self):
        event = {"Records": [{"messageId": "plain", "body": {"k": True}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("plain", '{"k":true}')])

    def test_body_string_decodes_to_records_json(self):
        body = json.dumps({"records": [{"payload": {"v": 1}}, {"payload": {"v": 2}}]})
        event = {"Records": [{"messageId": "B", "body": body}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("B", '{"v":1}'), ("B", '{"v":2}')])

    def test_body_string_decodes_to_container_whose_records_is_string(self):
        recs = json.dumps([{"payload": {"a": 1}}, {"payload": {"a": 2}}])
        container = {"records": recs}
        event = {"Records": [{"messageId": "S", "body": json.dumps(container)}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("S", '{"a":1}'), ("S", '{"a":2}')],
        )

    def test_body_string_cloudwatch_style_double_escaped(self):
        raw = '{\\n\\"records\\":[{\\n\\"payload\\":{\\"t\\":1}},{\\n\\"payload\\":{\\"t\\":2}}]}'
        event = {"Records": [{"messageId": "E", "body": raw}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("E", '{"t":1}'), ("E", '{"t":2}')])

    def test_body_string_json_list_payload(self):
        # body is a JSON array -> now treated as a payload (fix)
        event = {"Records": [{"messageId": "L", "body": '["x", 1]'}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("L", '["x",1]')])

    def test_bytes_and_bytearray_bodies(self):
        container = {"records": [{"payload": {"x": 1}}, {"payload": {"x": 2}}]}
        data = json.dumps(container).encode()
        e1 = {"Records": [{"messageId": "B1", "body": data}]}
        e2 = {"Records": [{"messageId": "B2", "body": bytearray(data)}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [("B1", '{"x":1}'), ("B1", '{"x":2}')])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [("B2", '{"x":1}'), ("B2", '{"x":2}')])

    # ---------------------------------------------------------------------
    # explode_sqs_event_to_payloads — guard / fallback paths
    # ---------------------------------------------------------------------

    def test_records_present_but_nonjson_string_fallback_to_whole_body(self):
        event = {"Records": [{"messageId": "bad", "body": {"version": "1", "records": "not-json"}}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("bad", '{"version":"1","records":"not-json"}')],
        )

    def test_body_is_nonjson_string_unrecognized(self):
        # body is a plain string that does not look like JSON → no results
        event = {"Records": [{"messageId": "U", "body": "hello"}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_payload_field_nonjson_string(self):
        # payload exists but is a non-JSON string → treated as scalar JSON
        event = {"Records": [{"messageId": "PNJ", "body": {"payload": "abc"}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("PNJ", '"abc"')])

    def test_records_contains_non_dict_items_are_ignored(self):
        event = {
            "Records": [
                {"messageId": "M", "body": {"records": [123, "abc", {"payload": {"ok": 1}}]}}
            ]
        }
        self.assertEqual(explode_sqs_event_to_payloads(event), [("M", '{"ok":1}')])

    def test_missing_messageid_missing_body_body_none_and_unrecognized_type(self):
        e1 = {"Records": [{"body": {"payload": {"a": 1}}}]}
        e2 = {"Records": [{"messageId": "m1"}]}
        e3 = {"Records": [{"messageId": "m2", "body": None}]}
        e4 = {"Records": [{"messageId": "m3", "body": 12345}]}
        e5 = {"Records": None}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [])
        self.assertEqual(explode_sqs_event_to_payloads(e3), [])
        self.assertEqual(explode_sqs_event_to_payloads(e4), [])
        self.assertEqual(explode_sqs_event_to_payloads(e5), [])

    def test_empty_inputs(self):
        self.assertEqual(explode_sqs_event_to_payloads({"Records": []}), [])
        self.assertEqual(explode_sqs_event_to_payloads({}), [])

    # ---------------------------------------------------------------------
    # _loads_multipass — decoding branches incl. fixes
    # ---------------------------------------------------------------------

    def test_loads_multipass_bytes_dict_string_of_string_and_quoted(self):
        obj = {"a": 1}
        self.assertEqual(_loads_multipass(obj), obj)
        self.assertEqual(_loads_multipass(json.dumps(obj).encode()), obj)
        s2 = json.dumps(json.dumps(obj))  # string-of-string
        self.assertEqual(_loads_multipass(s2), obj)
        quoted = '"{\\"b\\":2}"'          # quoted JSON
        self.assertEqual(_loads_multipass(quoted), {"b": 2})

    def test_loads_multipass_unicode_escape_success(self):
        raw = '{\\n  \\"obj\\": {\\"k\\": 1}\\n}'
        self.assertEqual(_loads_multipass(raw), {"obj": {"k": 1}})

    def test_loads_multipass_unicode_escape_transforms_nonjson(self):
        # contains \t → becomes a real tab after unicode_escape; still not JSON → transformed string
        s = "text\\tstill-not-json"
        self.assertEqual(_loads_multipass(s), "text\tstill-not-json")

    def test_loads_multipass_quoted_nonjson_remains_original(self):
        # With the fix, we *preserve* the quoted, non-JSON string
        s = '"not json"'
        self.assertEqual(_loads_multipass(s), '"not json"')

    def test_loads_multipass_no_progress_returns_original(self):
        self.assertEqual(_loads_multipass("plain text"), "plain text")

    # ---------------------------------------------------------------------
    # _flatten_records — recursion and string-peel
    # ---------------------------------------------------------------------

    def test_flatten_records_deep_and_string_inside(self):
        inner_list = json.dumps([{"payload": {"z": 1}}, {"payload": {"z": 2}}])
        records = [[[[inner_list]]], {"payload": {"z": 3}}]
        out = list(_flatten_records(records))
        vals = [d["payload"]["z"] for d in out]
        self.assertEqual(sorted(vals), [1, 2, 3])

    def test_flatten_records_nonjson_string_ignored(self):
        self.assertEqual(list(_flatten_records(["not-json"])), [])

    # ---------------------------------------------------------------------
    # _to_json_string — all categories
    # ---------------------------------------------------------------------

    def test_to_json_string_all_inputs(self):
        self.assertEqual(_to_json_string({"a": 1}), '{"a":1}')
        self.assertEqual(_to_json_string('{"x":3}'), '{"x":3}')
        self.assertEqual(_to_json_string(10), "10")
        self.assertEqual(_to_json_string("hello"), '"hello"')


if __name__ == "__main__":
    unittest.main()



