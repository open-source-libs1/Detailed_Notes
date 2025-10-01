




# -*- coding: utf-8 -*-
"""Pure helpers for extracting payloads from SQS events and mapping failures.

No network I/O here. Provides:
  • tolerant JSON parsing (double-encoded strings, stray backslashes/newlines)
  • extraction of ONLY `payload` objects from record bodies
  • flattening an event into (messageId, payload_json) pairs
  • mapping failed inner payloads back to the outer SQS messageId
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Tuple

logger = logging.getLogger(__name__)


def _try_json_unwrap(text: str) -> Tuple[Any, bool]:
    """Attempts up to 3 json.loads passes to unwrap double-encoded JSON strings.

    Args:
        text: A string that might itself be JSON, possibly double-encoded.

    Returns:
        Tuple[parsed_value, ok]:
          - parsed_value: last successfully parsed value (may be a str)
          - ok: True if the final parsed value is non-string JSON (dict/list/number/bool/null),
                False otherwise.

    Example:
        >>> _try_json_unwrap('"hello"')[0]
        'hello'
    """
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
      • For strings, try a sequence of sanitized candidates:
          1) original stripped
          2) remove CR/LF
          3) collapse multi-backslashes (e.g., '\\\\' → '\\')
          4) last resort: remove backslashes before quotes ( '\\"' → '"' )
        For each candidate, attempt up to 3 json.loads passes (unwrap double encoding).
      • If any candidate yields a non-string JSON value, return it.
      • Otherwise, if we decoded at least once to a string, return the last decoded string.
      • If all attempts fail, return the original input.

    Args:
        raw: Value that may be JSON or a JSON string.

    Returns:
        A Python object (dict, list, str, int, etc.) if successfully parsed, else the original value.

    Example:
        >>> _json_loads_relaxed(json.dumps(json.dumps({"a": 1})))
        {'a': 1}
        >>> _json_loads_relaxed('{\\\\\"k\\\\\":1}\\n')
        {'k': 1}
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


def _iter_payload_dicts_from_body(parsed: Any) -> Iterable[Any]:
    """Internal: yields payload values from a parsed body (dict/list/anything).

    Prefers entries within a top-level `records` list; also supports a root-level `payload`.
    Records without a `payload` key are ignored because we only forward payloads.
    """
    if isinstance(parsed, dict):
        recs = parsed.get("records")
        if isinstance(recs, list):
            for rec in recs:
                if isinstance(rec, dict) and "payload" in rec and rec["payload"] is not None:
                    yield rec["payload"]
        elif "payload" in parsed and parsed["payload"] is not None:
            yield parsed["payload"]

    elif isinstance(parsed, list):
        # list of micro-batches: [{"records":[...]}, {"records":[...]}]
        for item in parsed:
            yield from _iter_payload_dicts_from_body(item)


def extract_payloads_from_body(body: Any) -> List[str]:
    """Extracts ONLY `payload` messages from one SQS record `body`.

    The function:
      1) Parses `body` with `_json_loads_relaxed` if it is a string; otherwise uses as-is.
      2) Walks normalized structure and yields only the `payload` entries.
      3) If a payload value is itself a JSON string (possibly double-encoded), decode via `_json_loads_relaxed`.
      4) Serializes each payload to a compact JSON string (no newlines).

    Args:
        body: The `body` field from an outer SQS Record; can be dict/list/str.

    Returns:
        A list of JSON strings, one per extracted payload.

    Example:
        >>> body = {"records":[{"payload":{"id":1}}, {"payload":{"id":2}}]}
        >>> extract_payloads_from_body(body)
        ['{"id":1}', '{"id":2}']

        >>> body = '{"records":[{"payload":"{\\"k\\":1}"},{"payload":"{\\"k\\":2}"}]}'
        >>> extract_payloads_from_body(body)
        ['{"k":1}', '{"k":2}']
    """
    parsed = _json_loads_relaxed(body)
    out: List[str] = []

    for payload in _iter_payload_dicts_from_body(parsed):
        normalized = _json_loads_relaxed(payload)  # unwrap if payload is a JSON string
        try:
            out.append(json.dumps(normalized, separators=(",", ":"), ensure_ascii=False))
        except Exception:
            logger.error("Failed to serialize payload; forwarding as str")
            out.append(str(normalized))

    # Optional fallback: if there were no payloads but parsed is a dict/list, forward it
    if not out and isinstance(parsed, (dict, list)):
        out.append(json.dumps(parsed, separators=(",", ":"), ensure_ascii=False))

    return out


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
        ...     {"messageId":"A","body":{"records":[{"payload":{"id":1}},{"payload":{"id":2}}]}},
        ...     {"messageId":"B","body":'{"records":[{"payload":{"id":3}}]}'}
        ...   ]
        ... }
        >>> explode_sqs_event_to_payloads(event)
        [('A','{"id":1}'), ('A','{"id":2}'), ('B','{"id":3}')]
    """
    flat: List[Tuple[str, str]] = []
    for rec in event.get("Records", []):
        src_id = rec.get("messageId", "")
        body = rec.get("body", "")
        for msg in extract_payloads_from_body(body):
            flat.append((src_id, msg))
    return flat


def build_batch_item_failures(
    flattened_pairs: List[Tuple[str, str]],
    failed_bodies: List[str],
) -> List[Dict[str, str]]:
    """Builds the Lambda response for failed SQS payloads.

    Maps failed inner payload bodies back to their original outer `messageId`s.
    Ensures only one failure per outer `messageId` is reported, as required by
    SQS for partial-batch response handling.

    Args:
        flattened_pairs: List of (messageId, payload_json) pairs from
            `explode_sqs_event_to_payloads`.
        failed_bodies: List of payload bodies that failed to enqueue.

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





##############################################




# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest
from unittest.mock import patch

# Make <repo>/src importable
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from utils.helpers import (  # noqa: E402
    _try_json_unwrap,
    _json_loads_relaxed,
    _iter_payload_dicts_from_body,
    extract_payloads_from_body,
    explode_sqs_event_to_payloads,
    build_batch_item_failures,
)


class TestTryJsonUnwrap(unittest.TestCase):
    def test_try_unwrap_success_nonstring(self):
        parsed, ok = _try_json_unwrap("1")
        self.assertEqual(parsed, 1)
        self.assertTrue(ok)

    def test_try_unwrap_returns_string_not_ok(self):
        parsed, ok = _try_json_unwrap('"hi"')
        self.assertEqual(parsed, "hi")
        self.assertFalse(ok)


class TestJsonLoadsRelaxed(unittest.TestCase):
    def test_returns_non_string_unchanged(self):
        self.assertEqual(_json_loads_relaxed(123), 123)

    def test_double_encoded_object(self):
        inner = {"a": 1}
        double = json.dumps(json.dumps(inner))
        self.assertEqual(_json_loads_relaxed(double), inner)

    def test_backslashes_and_newlines(self):
        s = '{\\\\\"k\\\\\":1}\\n'
        self.assertEqual(_json_loads_relaxed(s), {"k": 1})

    def test_unparsable_returns_original(self):
        self.assertEqual(_json_loads_relaxed("<<bad>>"), "<<bad>>")


class TestIterPayloads(unittest.TestCase):
    def test_iter_from_records(self):
        src = {"records": [{"payload": 1}, {"payload": 2}]}
        items = list(_iter_payload_dicts_from_body(src))
        self.assertEqual(items, [1, 2])

    def test_iter_root_payload(self):
        src = {"payload": {"x": 5}}
        items = list(_iter_payload_dicts_from_body(src))
        self.assertEqual(items, [{"x": 5}])

    def test_iter_ignores_missing(self):
        src = {"records": [{"meta": 1}]}
        self.assertEqual(list(_iter_payload_dicts_from_body(src)), [])


class TestExtractPayloadsFromBody(unittest.TestCase):
    def test_two_payload_objects(self):
        body = {"records": [{"payload": {"id": 1}}, {"payload": {"id": 2}}]}
        msgs = extract_payloads_from_body(body)
        self.assertEqual([json.loads(m)["id"] for m in msgs], [1, 2])

    def test_double_encoded_payloads(self):
        body = {
            "records": [
                {"payload": json.dumps({"x": 10}).replace("\\", "\\\\") + "\n"},
                {"payload": json.dumps({"x": 20}).replace("\\", "\\\\")},
            ]
        }
        msgs = extract_payloads_from_body(json.dumps(body))
        self.assertEqual([json.loads(m)["x"] for m in msgs], [10, 20])

    def test_root_payload_fallback(self):
        body = {"payload": {"k": 1}}
        msgs = extract_payloads_from_body(body)
        self.assertEqual(msgs, ['{"k":1}'])

    def test_serialize_exception_fallback(self):
        body = {"records": [{"payload": {"k": 42}}]}
        real_dumps = json.dumps

        def flaky(obj, *a, **kw):
            if isinstance(obj, dict):
                raise TypeError("boom")
            return real_dumps(obj, *a, **kw)

        with patch("utils.helpers.json.dumps", side_effect=flaky):
            msgs = extract_payloads_from_body(body)
            self.assertEqual(msgs, ["{'k': 42}"])


class TestExplodeAndFailures(unittest.TestCase):
    def test_explode_payload_pairs(self):
        event = {
            "Records": [
                {"messageId": "A", "body": {"records": [{"payload": {"id": 1}}, {"payload": {"id": 2}}]}},
                {"messageId": "B", "body": '{"records":[{"payload":{"id":3}}]}'},
            ]
        }
        pairs = explode_sqs_event_to_payloads(event)
        self.assertEqual([(sid, json.loads(b)["id"]) for sid, b in pairs], [("A", 1), ("A", 2), ("B", 3)])

    def test_build_batch_item_failures_dedupes(self):
        flattened = [("A", '{"k":1}'), ("A", '{"k":2}'), ("B", '{"k":3}')]
        failed = ['{"k":2}', '{"k":3}']
        self.assertCountEqual(
            build_batch_item_failures(flattened, failed),
            [{"itemIdentifier": "A"}, {"itemIdentifier": "B"}],
        )

    def test_empty_event(self):
        self.assertEqual(explode_sqs_event_to_payloads({"Records": []}), [])


if __name__ == "__main__":
    unittest.main()


