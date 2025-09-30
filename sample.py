
# -*- coding: utf-8 -*-
"""Pure helpers for parsing SQS event bodies and mapping failures.

This module intentionally performs **no** network I/O. It provides:
  • tolerant JSON parsing (handles double-encoded JSON strings)
  • extraction of business messages from SQS `body` strings
  • flattening an entire Lambda `event` to (messageId, body) pairs
  • mapping failed inner message bodies back to outer SQS messageIds

Keep sender/orchestration logic in `handler.py` so the Lambda remains testable.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _json_loads_relaxed(raw: str) -> Any:
    """Parses a JSON string with tolerance for double-encoded or nested JSON.

    Attempts up to 3 passes of `json.loads`. If a later pass fails, returns the
    last successfully parsed object; if parsing never succeeds, returns `raw`
    unchanged. This is useful when producers double-encode payloads like
    `"{\\\"k\\\":1}"`.

    Args:
        raw: The raw string that may represent JSON.

    Returns:
        A Python object (dict, list, str, int, etc.) if successfully parsed,
        otherwise the original string.

    Example:
        >>> _json_loads_relaxed('"123"')
        '123'
        >>> _json_loads_relaxed(json.dumps(json.dumps({"a": 1})))
        {'a': 1}
        >>> _json_loads_relaxed('not-json')
        'not-json'
    """
    text = raw
    last_parsed = None
    for _ in range(3):
        try:
            parsed = json.loads(text)
            last_parsed = parsed
        except Exception:
            return last_parsed if last_parsed is not None else raw
        if isinstance(parsed, str):
            # It was a JSON string whose content might itself be JSON; try again.
            text = parsed
            continue
        # Parsed into a non-string (dict/list/number/bool/null) -> done.
        return parsed
    return last_parsed if last_parsed is not None else raw


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
      3) For each record, **prefers `record["payload"]`** if present; otherwise
         uses the entire record. If that chosen value is itself a JSON string,
         it is **decoded again** with `_json_loads_relaxed`.
      4) Serializes each chosen value to a compact JSON string for sending.

    Args:
        body: The raw `body` string from an SQS outer Record.

    Returns:
        A list of JSON strings, one per extracted business message.

    Example:
        >>> body = '{"records":[{"payload":{"account_key":"AK1"}},{"payload":{"account_key":"AK2"}}]}'
        >>> extract_messages_from_body(body)
        ['{"account_key":"AK1"}', '{"account_key":"AK2"}']

        >>> # Double-encoded payload is handled and unwrapped
        >>> dbl = '{"records":[{"payload":"{\\"k\\":1}"},{"payload":"{\\"k\\":2}"}]}'
        >>> extract_messages_from_body(dbl)
        ['{"k":1}', '{"k":2}']
    """
    parsed = _json_loads_relaxed(body)

    messages: List[str] = []
    for record in _extract_records_tree(parsed):
        chosen = record.get("payload", record)

        # If the chosen value is itself JSON encoded as a string, unwrap it.
        if isinstance(chosen, str):
            chosen = _json_loads_relaxed(chosen)

        try:
            messages.append(json.dumps(chosen, separators=(",", ":"), ensure_ascii=False))
        except Exception:
            logger.error("Failed to serialize payload/record; forwarding as str")
            messages.append(str(chosen))

    # If nothing matched but parsed value is a plain JSON string, forward that
    if not messages and isinstance(parsed, str):
        messages.append(parsed)

    return messages


def explode_sqs_event_to_messages(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Expands an SQS event into a flat list of (messageId, messageBody) pairs.

    Each outer SQS Record can contain multiple inner business messages inside its
    `body`. This function extracts them all and preserves a link to the outer
    `messageId` for later partial-failure reporting.

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

    Maps failed inner message bodies back to their original outer `messageId`s.
    Ensures only one failure per outer `messageId` is reported, as required by
    SQS for partial-batch response handling.

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




###########################


# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest

# Add <repo>/src to sys.path so `from utils.helpers import ...` resolves.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from utils.helpers import (  # noqa: E402
    _json_loads_relaxed,
    _extract_records_tree,
    extract_messages_from_body,
    explode_sqs_event_to_messages,
    build_batch_item_failures,
)


class TestJsonLoadsRelaxed(unittest.TestCase):
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


class TestExtractRecordsTree(unittest.TestCase):
    def test_common_records_array(self):
        obj = {"records": [{"payload": {"x": 1}}, {"payload": {"x": 2}}]}
        self.assertEqual(len(_extract_records_tree(obj)), 2)

    def test_list_of_batches(self):
        obj = [{"records": [{"payload": 1}]}, {"records": [{"payload": 2}, {"payload": 3}]}]
        self.assertEqual(len(_extract_records_tree(obj)), 3)

    def test_single_record_dict(self):
        self.assertEqual(len(_extract_records_tree({"meta": {"ref": "1:0"}})), 1)

    def test_ignores_strings(self):
        self.assertEqual(_extract_records_tree("nope"), [])


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

    def test_double_encoded_payloads_are_unwrapped_to_two_messages(self):
        # This mirrors your screenshot: two records, each payload is a JSON string (double-encoded).
        body = json.dumps({
            "version": 2,
            "batchMeta": {"schemaId": "x", "region": "1"},
            "records": [
                {"meta": {"ref": "1:0"}, "payload": json.dumps({
                    "account_key": "test_tban", "account_key_type": "TOKENIZEDDBAN",
                    "sor_id": "185", "is_enrollment_active": True,
                    "program_code": "TEST1234", "source_id": "BANK1"
                })},
                {"meta": {"ref": "1:0"}, "payload": json.dumps({
                    "account_key": "test_tban", "account_key_type": "TOKENIZEDDBAN",
                    "sor_id": "185", "is_enrollment_active": True,
                    "program_code": "TEST1234", "source_id": "BANK1"
                })}
            ]
        })
        msgs = extract_messages_from_body(body)
        self.assertEqual(len(msgs), 2)
        parsed = [json.loads(m) for m in msgs]
        self.assertEqual(parsed[0]["account_key"], "test_tban")
        self.assertTrue(parsed[0]["is_enrollment_active"])
        self.assertEqual(parsed[1]["program_code"], "TEST1234")


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

    def test_build_batch_item_failures_dedupes_by_outer_id(self):
        flattened = [("A", '{"k":1}'), ("A", '{"k":2}'), ("B", '{"k":3}')]
        failed = ['{"k":2}', '{"k":3}']
        self.assertCountEqual(
            build_batch_item_failures(flattened, failed),
            [{"itemIdentifier": "A"}, {"itemIdentifier": "B"}],
        )


if __name__ == "__main__":
    unittest.main()
