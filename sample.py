

# -*- coding: utf-8 -*-
"""Pure helpers for parsing SQS event bodies and mapping failures.

This module intentionally performs **no** network I/O. It provides:
  • tolerant JSON parsing (double-encoded JSON strings, stray backslashes, newlines)
  • extraction of business messages from SQS `body` strings
  • flattening an entire Lambda `event` to (messageId, body) pairs
  • mapping failed inner message bodies back to outer SQS messageIds
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _try_json_unwrap(text: str) -> Any:
    """Attempt up to 3 json.loads passes to unwrap double-encoded JSON strings."""
    last_parsed = None
    for _ in range(3):
        try:
            parsed = json.loads(text)
            last_parsed = parsed
        except Exception:
            return last_parsed, False
        if isinstance(parsed, str):
            text = parsed
            continue
        return parsed, True
    return last_parsed, not isinstance(last_parsed, str)


def _json_loads_relaxed(raw: Any) -> Any:
    """Parses JSON with tolerance for double-encoded, escaped, or newline-padded content.

    Strategy:
      • Non-strings are returned unchanged.
      • For strings, build a sequence of *sanitized candidates* and try each:
          1) original stripped
          2) remove CR/LF
          3) collapse multi-backslashes (e.g., '\\\\' → '\\')
          4) as a last resort, remove backslashes before quotes (e.g., '\\"' → '"')
        For each candidate, attempt up to 3 json.loads passes to unwrap double encoding.
      • If any candidate yields a non-string JSON value, return it.
      • Otherwise, if we decoded at least once to a string, return the last decoded string.
      • If all attempts fail, return the original input.

    Args:
        raw: Value that may be JSON or a JSON string.

    Returns:
        A Python object (dict, list, str, int, etc.) if successfully parsed, else the original value.

    Example:
        >>> _json_loads_relaxed('"123"')
        '123'
        >>> _json_loads_relaxed(json.dumps(json.dumps({"a": 1})))
        {'a': 1}
        >>> _json_loads_relaxed('{\\\\\"k\\\\\":1}\\n')
        {'k': 1}
        >>> _json_loads_relaxed('not-json')
        'not-json'
    """
    if not isinstance(raw, str):
        return raw

    base = raw.strip()

    candidates: List[str] = [base]

    no_newlines = base.replace("\n", "").replace("\r", "")
    if no_newlines != base:
        candidates.append(no_newlines)

    collapsed = re.sub(r"\\{2,}", r"\\", no_newlines)
    if collapsed not in candidates:
        candidates.append(collapsed)

    unescape_quotes = collapsed.replace('\\"', '"')
    if unescape_quotes not in candidates:
        candidates.append(unescape_quotes)

    last_str: Any = None
    for cand in candidates:
        parsed, ok = _try_json_unwrap(cand)
        if ok:
            return parsed
        if isinstance(parsed, str):
            last_str = parsed

    return last_str if last_str is not None else raw


def _extract_records_tree(obj: Any) -> List[Dict[str, Any]]:
    """Normalizes various shapes into a list of record dictionaries.

    Handles cases where the object is:
      - A dict with a "records" list
      - A list of dicts containing "records"
      - A single record dict
      - Anything else → returns empty list

    Args:
        obj: A parsed Python object (dict, list, str, etc.).

    Returns:
        A list of dictionaries representing records.

    Example:
        >>> _extract_records_tree({"records":[{"payload":{"x":1}},{"payload":{"x":2}}]})
        [{'payload': {'x': 1}}, {'payload': {'x': 2}}]
        >>> _extract_records_tree([{"records":[{"payload":1}]}])
        [{'payload': 1}]
    """
    out: List[Dict[str, Any]] = []

    if isinstance(obj, dict):
        if isinstance(obj.get("records"), list):
            for rec in obj["records"]:
                if isinstance(rec, dict):
                    out.append(rec)
        else:
            out.append(obj)

    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and isinstance(item.get("records"), list):
                for rec in item["records"]:
                    if isinstance(rec, dict):
                        out.append(rec)
            elif isinstance(item, dict):
                out.append(item)

    return out


def extract_messages_from_body(body: str) -> List[str]:
    """Extracts individual messages from one SQS record `body`.

    The function:
      1) Parses `body` with `_json_loads_relaxed` (handles double-encoded JSON).
      2) Flattens to record dicts via `_extract_records_tree`.
      3) For each record, **prefers `record["payload"]`** if present; otherwise uses the entire record.
      4) If the chosen value is a JSON-encoded string, unwraps it via `_json_loads_relaxed`.
      5) Serializes each chosen value to a compact JSON string for sending.

    Args:
        body: The raw `body` string from an SQS outer Record.

    Returns:
        A list of JSON strings, one per extracted business message.

    Example:
        >>> body = '{"records":[{"payload":{"account_key":"AK1"}},{"payload":{"account_key":"AK2"}}]}'
        >>> extract_messages_from_body(body)
        ['{"account_key":"AK1"}', '{"account_key":"AK2"}']

        >>> dbl = '{"records":[{"payload":"{\\"k\\":1}"},{"payload":"{\\"k\\":2}"}]}'
        >>> extract_messages_from_body(dbl)
        ['{"k":1}', '{"k":2}']
    """
    parsed = _json_loads_relaxed(body)
    messages: List[str] = []

    for record in _extract_records_tree(parsed):
        chosen = record.get("payload", record)
        if isinstance(chosen, str):
            chosen = _json_loads_relaxed(chosen)
        try:
            messages.append(json.dumps(chosen, separators=(",", ":"), ensure_ascii=False))
        except Exception:
            logger.error("Failed to serialize payload/record; forwarding as str")
            messages.append(str(chosen))

    if not messages and isinstance(parsed, str):
        messages.append(parsed)

    return messages


def explode_sqs_event_to_messages(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Expands an SQS event into a flat list of (messageId, messageBody) pairs.

    Args:
        event: The full Lambda event payload containing `Records`.

    Returns:
        A list of (source_message_id, body_json_string) tuples.

    Example:
        >>> event = {
        ...   "Records": [
        ...     {"messageId":"A","body":'{"records":[{"payload":{"id":1}},{"payload":{"id":2}}]}'},
        ...     {"messageId":"B","body":'{"records":[{"payload":{"id":3}}]}'}
        ...   ]
        ... }
        >>> explode_sqs_event_to_messages(event)
        [('A','{"id":1}'), ('A','{"id":2}'), ('B','{"id":3}')]
    """
    flat: List[Tuple[str, str]] = []
    for rec in event.get("Records", []):
        src_id = rec.get("messageId", "")
        body = rec.get("body", "")
        for msg in extract_messages_from_body(body):
            flat.append((src_id, msg))
    return flat


def build_batch_item_failures(
    flattened_pairs: List[Tuple[str, str]],
    failed_bodies: List[str],
) -> List[Dict[str, str]]:
    """Builds the Lambda response for failed SQS messages.

    Args:
        flattened_pairs: List of (messageId, body) pairs from
            `explode_sqs_event_to_messages`.
        failed_bodies: List of message bodies that failed to enqueue.

    Returns:
        A list of dicts in the format required by Lambda:
        `[{ "itemIdentifier": "<outer-messageId>" }, ...]`.

    Example:
        >>> flattened = [('A','{"id":1}'), ('A','{"id":2}'), ('B','{"id":3}')]
        >>> failed_bodies = ['{"id":2}','{"id":3}']
        >>> build_batch_item_failures(flattened, failed_bodies)
        [{'itemIdentifier': 'A'}, {'itemIdentifier': 'B'}]
    """
    failures: List[Dict[str, str]] = []
    failed_set = set(failed_bodies)
    seen_ids = set()

    for src_id, body in flattened_pairs:
        if body in failed_set and src_id not in seen_ids:
            failures.append({"itemIdentifier": src_id})
            seen_ids.add(src_id)

    return failures





#################################################


# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest
from unittest.mock import patch

# Add <repo>/src to sys.path so `from utils.helpers import ...` resolves.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from utils.helpers import (  # noqa: E402
    _try_json_unwrap,
    _json_loads_relaxed,
    _extract_records_tree,
    extract_messages_from_body,
    explode_sqs_event_to_messages,
    build_batch_item_failures,
)


class TestTryJsonUnwrap(unittest.TestCase):
    def test_try_unwrap_success_nonstring(self):
        parsed, ok = _try_json_unwrap("1")
        self.assertEqual(parsed, 1)
        self.assertTrue(ok)

    def test_try_unwrap_last_success_string_not_ok(self):
        # First pass yields a plain string, second pass fails -> ok == False
        parsed, ok = _try_json_unwrap('"hello"')
        self.assertEqual(parsed, "hello")
        self.assertFalse(ok)


class TestJsonLoadsRelaxed(unittest.TestCase):
    def test_returns_non_string_unchanged(self):
        self.assertEqual(_json_loads_relaxed(123), 123)

    def test_single_encoded_string(self):
        self.assertEqual(_json_loads_relaxed('"hello"'), "hello")

    def test_double_encoded_object(self):
        inner = {"a": 1}
        double = json.dumps(json.dumps(inner))
        self.assertEqual(_json_loads_relaxed(double), inner)

    def test_number_and_null(self):
        self.assertEqual(_json_loads_relaxed("123"), 123)
        self.assertIsNone(_json_loads_relaxed("null"))

    def test_unparsable_returns_input(self):
        self.assertEqual(_json_loads_relaxed("<<bad>>"), "<<bad>>")

    def test_backslashes_and_newlines_are_normalized(self):
        s = '{\\\\\"k\\\\\":1}\\n'  # becomes {\"k\":1}\n at runtime
        parsed = _json_loads_relaxed(s)
        self.assertEqual(parsed, {"k": 1})

    def test_last_success_returns_decoded_string(self):
        # '"hi"' -> first pass 'hi' (string), second pass fails, so return 'hi'
        self.assertEqual(_json_loads_relaxed('"hi"'), "hi")


class TestExtractRecordsTree(unittest.TestCase):
    def test_common_records_array(self):
        obj = {"records": [{"payload": {"x": 1}}, {"payload": {"x": 2}}]}
        self.assertEqual(len(_extract_records_tree(obj)), 2)

    def test_list_of_batches(self):
        obj = [{"records": [{"payload": 1}]}, {"records": [{"payload": 2}, {"payload": 3}]}]
        self.assertEqual(len(_extract_records_tree(obj)), 3)

    def test_single_record_dict(self):
        self.assertEqual(len(_extract_records_tree({"meta": {"ref": "1:0"}})), 1)

    def test_list_of_plain_records(self):
        obj = [{"payload": {"p": 1}}, {"payload": {"p": 2}}]
        self.assertEqual(len(_extract_records_tree(obj)), 2)

    def test_ignores_strings_and_empty(self):
        self.assertEqual(_extract_records_tree("nope"), [])
        self.assertEqual(_extract_records_tree([]), [])


class TestExtractMessagesFromBody(unittest.TestCase):
    def test_prefers_payload(self):
        body = json.dumps({"records": [{"payload": {"k": 1}}, {"payload": {"k": 2}}]})
        msgs = extract_messages_from_body(body)
        self.assertEqual([json.loads(m)["k"] for m in msgs], [1, 2])

    def test_fallback_to_record(self):
        body = json.dumps({"records": [{"meta": {"a": 1}}, {"meta": {"a": 2}}]})
        msgs = extract_messages_from_body(body)
        self.assertEqual([json.loads(m)["meta"]["a"] for m in msgs], [1, 2])

    def test_plain_json_string_no_records(self):
        self.assertEqual(extract_messages_from_body(json.dumps("just a json string")), ["just a json string"])

    def test_double_encoded_payloads_two_messages(self):
        payload_dict = {
            "account_key": "test_tban",
            "account_key_type": "TOKENIZEDDBAN",
            "sor_id": "185",
            "is_enrollment_active": True,
            "program_code": "TEST1234",
            "source_id": "BANK1",
        }
        noisy = json.dumps(payload_dict).replace("\\", "\\\\") + "\n"
        body = json.dumps({
            "version": 2,
            "batchMeta": {"schemaId": "x", "region": "1"},
            "records": [
                {"meta": {"ref": "1:0"}, "payload": noisy},
                {"meta": {"ref": "1:0"}, "payload": noisy},
            ],
        })
        msgs = extract_messages_from_body(body)
        self.assertEqual(len(msgs), 2)
        parsed = [json.loads(m) for m in msgs]
        self.assertEqual(parsed[0]["account_key"], "test_tban")
        self.assertTrue(parsed[0]["is_enrollment_active"])
        self.assertEqual(parsed[1]["program_code"], "TEST1234")

    def test_serialize_exception_falls_back_to_str(self):
        body = json.dumps({"records": [{"payload": {"k": 1}}]})

        # Patch json.dumps to raise only when called on dicts (chosen will be a dict)
        real_dumps = json.dumps

        def flaky(obj, *a, **kw):
            if isinstance(obj, dict):
                raise TypeError("boom")
            return real_dumps(obj, *a, **kw)

        with patch("utils.helpers.json.dumps", side_effect=flaky):
            msgs = extract_messages_from_body(body)
            # When serialization fails, we append str(chosen) → single quotes expected
            self.assertEqual(msgs, ["{'k': 1}"])


class TestExplodeAndFailures(unittest.TestCase):
    def test_explode_event_pairs(self):
        event = {
            "Records": [
                {"messageId": "A", "body": json.dumps({"records": [{"payload": {"id": 1}}, {"payload": {"id": 2}}]})},
                {"messageId": "B", "body": json.dumps({"records": [{"payload": {"id": 3}}]})},
            ]
        }
        pairs = explode_sqs_event_to_messages(event)
        self.assertEqual([(sid, json.loads(b)["id"]) for sid, b in pairs], [("A", 1), ("A", 2), ("B", 3)])

    def test_explode_handles_empty_event(self):
        self.assertEqual(explode_sqs_event_to_messages({"Records": []}), [])

    def test_build_batch_item_failures_dedupes_and_ignores_unknown(self):
        flattened = [("A", '{"k":1}'), ("A", '{"k":2}'), ("B", '{"k":3}')]
        failed = ['{"k":2}', '{"k":999}', '{"k":3}']  # 999 is unknown and ignored
        self.assertCountEqual(
            build_batch_item_failures(flattened, failed),
            [{"itemIdentifier": "A"}, {"itemIdentifier": "B"}],
        )


if __name__ == "__main__":
    unittest.main()


