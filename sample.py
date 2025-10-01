from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Tuple, Union, Optional

logger = logging.getLogger(__name__)

Jsonable = Union[dict, list, str, int, float, bool, None]


def explode_sqs_event_to_payloads(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Expands an SQS event into a flat list of **(messageId, payload_json)** pairs.

    Explanation:
        Each outer SQS Record can contain multiple inner payloads inside its `body`.
        Bodies may be dicts, lists, JSON strings (often double-escaped), or even
        **malformed wrappers** where the outer JSON fails to parse but the inner
        `"payload":"{...}"`/`"payload":{...}` chunks are valid JSON (your Event-1).
        This function normalizes all those cases and returns **only the payload JSON**
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

        # 1) Normal case: {"records": [...]}
        extracted = False
        if isinstance(body_obj, dict) and "records" in body_obj:
            recs = body_obj["records"]
            if not isinstance(recs, (list, dict)):
                recs = _loads_multipass(recs)
            for inner in _flatten_records(recs):
                if isinstance(inner, dict) and "payload" in inner:
                    payload_obj = _loads_multipass(inner["payload"])
                    results.append((msg_id, _to_json_string(payload_obj)))
                    extracted = True
        if extracted:
            continue

        # 2) Body is {"payload": ...} (payload may itself contain records)
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
            results.append((msg_id, _to_json_string(payload_obj)))
            continue

        # 3) Dict/list bodies → treat as single payloads
        if isinstance(body_obj, dict):
            results.append((msg_id, _to_json_string(body_obj)))
            continue
        if isinstance(body_obj, list):
            results.append((msg_id, _to_json_string(body_obj)))
            continue

        # 4) JSON-looking string
        if isinstance(body_obj, str) and _looks_like_json(body_obj):
            peeled = _loads_multipass(body_obj)

            # 4a) Peeled to {"records": ...}
            if isinstance(peeled, dict) and "records" in peeled:
                recs3 = peeled["records"]
                if not isinstance(recs3, (list, dict)):
                    recs3 = _loads_multipass(recs3)
                any3 = False
                for inner in _flatten_records(recs3):
                    if isinstance(inner, dict) and "payload" in inner:
                        inner_payload = _loads_multipass(inner["payload"])
                        results.append((msg_id, _to_json_string(inner_payload)))
                        any3 = True
                if any3:
                    continue

            # 4b) Peeled is *still* a string → outer JSON malformed; salvage payloads
            if isinstance(peeled, str):
                salvaged = list(_salvage_payloads(peeled))
                if salvaged:
                    for p in salvaged:
                        results.append((msg_id, _to_json_string(p)))
                    continue

            # 4c) Fallback: whatever `peeled` is (number/bool/null/str/json)
            results.append((msg_id, _to_json_string(peeled)))
            continue

        logger.debug("Unrecognized body shape for messageId=%s: %r", msg_id, type(body_obj))

    return results


def _loads_multipass(value: Any, *, max_passes: int = 8) -> Jsonable:
    """Decode JSON across multiple escaping layers with graceful fallbacks.

    Explanation:
        CloudWatch/SQS bodies often arrive double-escaped (e.g., literal \\n and \").
        This function repeatedly attempts to decode JSON, peeling one layer at a time:
        - bytes/bytearray -> utf-8 string
        - json.loads if possible
        - if json.loads returns a string that *looks like* JSON, peel again
        - otherwise for strings: remove one layer of quotes, unicode-escape the content
        - stop when no progress is possible or a non-string JSON value is reached

    Args:
        value: Any object possibly containing JSON across multiple encodings.
        max_passes: Max iterations when peeling nested encodings.

    Returns:
        A JSON-able Python object (dict/list/str/number/bool/None).

    Example:
        >>> _loads_multipass('"{\\"a\\":1}"')
        {'a': 1}
    """
    cur: Any = value

    if isinstance(cur, (bytes, bytearray)):
        cur = cur.decode("utf-8", errors="replace")

    if isinstance(cur, (dict, list)):
        return cur

    for _ in range(max_passes):
        if isinstance(cur, (dict, list)):
            return cur
        if not isinstance(cur, str):
            return cur

        s = cur.strip()

        # Try plain JSON first
        try:
            decoded = json.loads(s, strict=False)
            if isinstance(decoded, str):
                # Nested JSON string? Keep peeling only if it *looks* like JSON
                if _looks_like_json(decoded.strip()):
                    cur = decoded
                    continue
                # Non-JSON string → preserve original 'cur' to avoid over-mutating
                return cur
            return decoded
        except json.JSONDecodeError:
            pass

        transformed = False

        # Remove one outer quote layer if present
        if s and s[0] == s[-1] == '"':
            s = s[1:-1]
            transformed = True

        # Convert visible escapes (\n, \") into real characters
        if "\\" in s:
            try:
                s2 = bytes(s, "utf-8").decode("unicode_escape")
                s = s2
                transformed = True
            except Exception:
                pass

        if not transformed:
            return cur

        cur = s  # iterate again

    return cur


def _flatten_records(records_field: Any) -> Iterator[dict]:
    """Iterate over dict items inside a `records` field, robust to wrappers.

    Explanation:
        `records` may be a list, list-of-lists/tuples, a dict wrapper that itself contains
        `records`, or even a stringified container. This function consistently yields the
        inner dict items so callers can pick out `payload`.

    Args:
        records_field: The object found under some `...["records"]` key.

    Returns:
        An iterator over the dict items contained within `records`.

    Example:
        >>> list(_flatten_records([{"payload":{"x":1}}, [{"payload":{"x":2}}]]))
        [{'payload': {'x': 1}}, {'payload': {'x': 2}}]
    """
    def _walk(obj: Any) -> Iterator[dict]:
        if isinstance(obj, str) and _looks_like_json(obj):
            obj = _loads_multipass(obj)

        if isinstance(obj, dict) and "records" in obj:
            yield from _walk(obj["records"])
            return

        if isinstance(obj, dict):
            yield obj
            return

        if isinstance(obj, (list, tuple)):
            for item in obj:
                yield from _walk(item)
            return
        # other scalars: ignore

    yield from _walk(records_field)


def _looks_like_json(s: str) -> bool:
    """Quick check: does a string appear to be JSON?

    Args:
        s: Input string.

    Returns:
        True if `s` begins with '{' or '[' after leading whitespace; else False.

    Example:
        >>> _looks_like_json('{"a":1}')
        True
    """
    s = s.lstrip()
    return s.startswith("{") or s.startswith("[")


def _to_json_string(obj: Jsonable) -> str:
    """Normalize any JSON-able value into a compact JSON string.

    Args:
        obj: A JSON-able Python object.

    Returns:
        A compact JSON string; strings that already look like JSON are returned as-is.

    Example:
        >>> _to_json_string({"a":1})
        '{"a":1}'
    """
    if isinstance(obj, str) and _looks_like_json(obj.strip()):
        return obj
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# -------------------- Salvage for malformed outer bodies -------------------- #

def _salvage_payloads(text: str) -> Iterator[Jsonable]:
    """Extract `payload` objects from a malformed body text.

    Explanation:
        Handles both `"payload":"{...}"` (quoted) and `"payload":{...}` (unquoted)
        even when the outer JSON is broken (e.g., inner quotes are not escaped).
        We DO NOT try to parse the quoted value boundary; instead we jump to the
        next '{' and slice the balanced object with a quote/escape-aware matcher.

    Args:
        text: Malformed outer body string (still a str after _loads_multipass).

    Returns:
        Iterator of parsed payload objects (usually dicts).

    Example:
        >>> list(_salvage_payloads('"payload":"{\\"a\\":1}","x":0,"payload":{"b":2}'))
        [{'a': 1}, {'b': 2}]
    """
    def find_matching_brace(s: str, start: int) -> Optional[int]:
        depth = 0
        i = start
        in_str = False
        esc = False
        while i < len(s):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
            i += 1
        return None

    key = '"payload"'
    i = 0
    n = len(text)
    while True:
        k = text.find(key, i)
        if k == -1:
            return
        colon = text.find(":", k + len(key))
        if colon == -1:
            return

        # Move to start of the value; allow whitespace and an optional opening quote.
        j = colon + 1
        while j < n and text[j] in " \t\r\n":
            j += 1
        if j < n and text[j] == '"':
            j += 1
            while j < n and text[j] in " \t\r\n":
                j += 1

        # Hunt forward to the next '{'
        obj_start = text.find("{", j)
        if obj_start == -1:
            i = k + len(key)
            continue

        obj_end = find_matching_brace(text, obj_start)
        if obj_end is None:
            i = k + len(key)
            continue

        fragment = text[obj_start : obj_end + 1]
        parsed = _loads_multipass(fragment)
        if isinstance(parsed, (dict, list)):
            yield parsed

        i = obj_end + 1




####################################



import json
import unittest

from src.utils.helpers import (
    explode_sqs_event_to_payloads,
    _loads_multipass,
    _flatten_records,
    _looks_like_json,
    _to_json_string,
    _salvage_payloads,
)


class TestHelpersSimplified(unittest.TestCase):
    # ---------------- explode_sqs_event_to_payloads ----------------

    def test_multiple_payloads_from_records(self):
        event = {
            "Records": [{
                "messageId": "A",
                "body": {"records": [{"payload": {"p": 1}}, {"payload": {"p": 2}}]}
            }]
        }
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("A", '{"p":1}'), ("A", '{"p":2}')]
        )

    def test_lowercase_messageid_and_records_is_dict(self):
        event = {"Records": [{"messageid": "x", "body": {"records": {"payload": {"x": 1}}}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("x", '{"x":1}')])

    def test_records_nested_lists_and_stringified(self):
        inner = json.dumps([{"payload": {"z": 9}}])
        event = {
            "Records": [{
                "messageId": "deep",
                "body": {"records": [[{"payload": {"z": 7}}], [[inner]]]}
            }]
        }
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("deep", '{"z":7}'), ("deep", '{"z":9}')]
        )

    def test_payload_field_simple_and_payload_contains_records(self):
        inner = {"records": [{"payload": {"q": 5}}, {"payload": {"q": 6}}]}
        e1 = {"Records": [{"messageId": "simple", "body": {"payload": {"v": 10}}}]}
        e2 = {"Records": [{"messageId": "nested", "body": {"payload": json.dumps(inner)}}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [("simple", '{"v":10}')])
        self.assertEqual(
            explode_sqs_event_to_payloads(e2),
            [("nested", '{"q":5}'), ("nested", '{"q":6}')]
        )

    def test_body_dict_without_records_or_payload(self):
        event = {"Records": [{"messageId": "plain", "body": {"k": True}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("plain", '{"k":true}')])

    def test_body_string_decodes_to_records_json(self):
        body = json.dumps({"records": [{"payload": {"v": 1}}, {"payload": {"v": 2}}]})
        event = {"Records": [{"messageId": "B", "body": body}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("B", '{"v":1}'), ("B", '{"v":2}')]
        )

    def test_body_string_container_whose_records_is_string(self):
        recs = json.dumps([{"payload": {"a": 1}}, {"payload": {"a": 2}}])
        container = {"records": recs}
        event = {"Records": [{"messageId": "S", "body": json.dumps(container)}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("S", '{"a":1}'), ("S", '{"a":2}')]
        )

    def test_body_list_payload_and_bytes(self):
        e1 = {"Records": [{"messageId": "L", "body": '["x", 1]'}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [("L", '["x",1]')])

        container = {"records": [{"payload": {"x": 1}}, {"payload": {"x": 2}}]}
        data = json.dumps(container).encode()
        e2 = {"Records": [{"messageId": "B", "body": data}]}
        e3 = {"Records": [{"messageId": "BA", "body": bytearray(data)}]}
        self.assertEqual(explode_sqs_event_to_payloads(e2), [("B", '{"x":1}'), ("B", '{"x":2}')])
        self.assertEqual(explode_sqs_event_to_payloads(e3), [("BA", '{"x":1}'), ("BA", '{"x":2}')])

    def test_plain_string_body_unrecognized_and_missing_fields(self):
        e1 = {"Records": [{"messageId": "U", "body": "hello"}]}
        e2 = {"Records": [{"body": {"payload": {"a": 1}}}]}
        e3 = {"Records": [{"messageId": "m2", "body": None}]}
        e4 = {"Records": [{"messageId": "m3", "body": 12345}]}
        e5 = {"Records": None}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [])
        self.assertEqual(explode_sqs_event_to_payloads(e3), [])
        self.assertEqual(explode_sqs_event_to_payloads(e4), [])
        self.assertEqual(explode_sqs_event_to_payloads(e5), [])

    # ---------------- salvage-focused tests (expand coverage) ----------------

    def test_salvage_payloads_direct(self):
        # Exactly the pattern from your failing test: first quoted, second unquoted.
        text = '"payload":"{\\"a\\":1}","x":0,"payload":{"b":2}'
        objs = list(_salvage_payloads(text))
        self.assertEqual(objs, [{"a": 1}, {"b": 2}])

    def test_salvage_handles_extra_ws_and_newlines(self):
        text = '"payload"  :  "  {\\n  \\"k\\": 3 }  " , "payload" :  { "m" : 4 }'
        objs = list(_salvage_payloads(text))
        self.assertEqual(objs, [{"k": 3}, {"m": 4}])

    def test_salvage_handles_quad_backslashes_then_unescape(self):
        # Simulates a doubly-escaped quoted object inside a broken body.
        text = '"payload":"{\\\\\\"u\\\\\\":5}","payload":{"v":6}'
        # After unicode_escape twice -> {"u":5}
        objs = list(_salvage_payloads(text))
        self.assertEqual(objs, [{"u": 5}, {"v": 6}])

    def test_salvage_ignores_unbalanced_or_missing_object(self):
        text = '"payload":"{ \\"bad\\": 1", "payload": 123, "payload":"notjson"'
        objs = list(_salvage_payloads(text))
        self.assertEqual(objs, [])  # nothing salvageable

    # ---------------- _loads_multipass core paths ----------------

    def test_loads_multipass_paths(self):
        obj = {"a": 1}
        self.assertEqual(_loads_multipass(obj), obj)
        self.assertEqual(_loads_multipass(json.dumps(obj).encode()), obj)
        doubly = json.dumps(json.dumps(obj))
        self.assertEqual(_loads_multipass(doubly), obj)
        quoted_json = '"{\\"b\\":2}"'
        self.assertEqual(_loads_multipass(quoted_json), {"b": 2})
        raw = '{\\n  \\"obj\\": {\\"k\\": 1}\\n}'
        self.assertEqual(_loads_multipass(raw), {"obj": {"k": 1}})
        quoted_nonjson = '"not json"'
        self.assertEqual(_loads_multipass(quoted_nonjson), '"not json"')
        self.assertEqual(_loads_multipass("\\xZZ"), "\\xZZ")
        self.assertEqual(_loads_multipass('"{bad json}"'), "{bad json}")
        self.assertEqual(_loads_multipass("plain text"), "plain text")

    # ---------------- _flatten_records / helpers ----------------

    def test_flatten_records_variations_and_helpers(self):
        inner_list = json.dumps([{"payload": {"z": 1}}, {"payload": {"z": 2}}])
        records = [[[[inner_list]]], {"payload": {"z": 3}}, ("ignore",)]
        out = list(_flatten_records(records))
        vals = [d["payload"]["z"] for d in out]
        self.assertEqual(sorted(vals), [1, 2, 3])

        self.assertTrue(_looks_like_json('{"a":1}'))
        self.assertTrue(_looks_like_json('[1,2]'))
        self.assertFalse(_looks_like_json('not json'))
        self.assertEqual(_to_json_string({"a": 1}), '{"a":1}')
        self.assertEqual(_to_json_string('{"x":3}'), '{"x":3}')
        self.assertEqual(_to_json_string(10), "10")
        self.assertEqual(_to_json_string("hello"), '"hello"')


if __name__ == "__main__":
    unittest.main()


