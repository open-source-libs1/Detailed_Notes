# -*- coding: utf-8 -*-
"""
Pure helpers for:
  • robustly parsing SQS event bodies (handles double-escaped JSON)
  • flattening to a list of messages
  • mapping failed bodies back to original SQS messageIds
No SQS calls happen here.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# -------------------- parsing utilities --------------------

def _json_loads_relaxed(raw: str) -> Any:
    """
    Parse `raw` as JSON, tolerating double-encoded strings (up to 3 passes).
    If parsing ultimately fails, return the original string.
    """
    text = raw
    for _ in range(3):
        try:
            parsed = json.loads(text)
        except Exception:
            break
        if isinstance(parsed, str):  # still stringified JSON → try again
            text = parsed
            continue
        return parsed
    return raw


def _extract_records_tree(obj: Any) -> List[Dict[str, Any]]:
    """
    Normalize into a list of *record* dicts. Supports:
      1) {"records":[ {...}, {...} ]}
      2) [{"records":[...]} , {"records":[...]}]
      3) a single record dict {...}
    Unknown shapes → empty list.
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
    """
    Parse ONE SQS record['body'] into JSON strings to forward.
    Preference:
      • if record has 'payload' -> forward payload
      • else forward the entire record
    """
    parsed = _json_loads_relaxed(body)
    messages: List[str] = []

    for rec in _extract_records_tree(parsed):
        payload = rec.get("payload", rec)
        try:
            messages.append(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
        except Exception:
            logger.error("Failed to serialize payload/record; forwarding as str")
            messages.append(str(payload))

    # If nothing matched but body itself is a JSON string, forward that
    if not messages and isinstance(parsed, str):
        messages.append(parsed)

    return messages


def explode_sqs_event_to_messages(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Expand AWS SQS event into a flat list of (source_message_id, body_json_str).
    """
    flat: List[Tuple[str, str]] = []
    for rec in event.get("Records", []):
        src_id = rec.get("messageId", "")
        body = rec.get("body", "")
        for msg in extract_messages_from_body(body):
            flat.append((src_id, msg))
    return flat


# -------------------- failure mapping --------------------

def build_batch_item_failures(
    flattened_pairs: List[Tuple[str, str]],
    failed_bodies: List[str],
) -> List[Dict[str, str]]:
    """
    Translate failed message *bodies* back to Lambda 'batchItemFailures' using
    the original source messageIds. Only one failure per source id is emitted.
    """
    failures: List[Dict[str, str]] = []
    failed_set = set(failed_bodies)
    seen_ids = set()

    for src_id, body in flattened_pairs:
        if body in failed_set and src_id not in seen_ids:
            failures.append({"itemIdentifier": src_id})
            seen_ids.add(src_id)

    return failures





#############################################


from helpers.message_extractor import (
    explode_sqs_event_to_messages,
    build_batch_item_failures,
)


def lambda_handler(event, context):
    logger.info("Processing message batch of size %d", len(event.get("Records", [])))

    # 1) Flatten each incoming SQS body's internal batch into individual messages
    flattened = explode_sqs_event_to_messages(event)  # [(src_id, body_json), ...]
    bodies = [b for _, b in flattened]
    logger.debug("Flattened %d messages from %d Records", len(bodies), len(event.get("Records", [])))

    # 2) Use the existing concurrent pusher (unchanged) to forward to destination SQS
    failed_bodies = push_batch_to_sqs_concurrently(sqs, queue_url, bodies)

    # 3) Map failed bodies back to original source messageIds for partial retry
    batch_item_failures = build_batch_item_failures(flattened, failed_bodies)

    logger.info(
        "Successfully processed %d messages. Reporting %d failures back to original SQS",
        len(bodies), len(batch_item_failures),
    )
    return {"batchItemFailures": batch_item_failures}




######################################################


# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest

# make 'src' importable like your current tests do
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from helpers.message_extractor import (  # noqa: E402
    _json_loads_relaxed,
    _extract_records_tree,
    extract_messages_from_body,
    explode_sqs_event_to_messages,
    build_batch_item_failures,
)


class TestParsingUtilities(unittest.TestCase):
    def test_relaxed_json_double_escaped(self):
        inner = {"records": [{"payload": {"a": 1}}]}
        double = json.dumps(json.dumps(inner))
        parsed = _json_loads_relaxed(double)
        self.assertIsInstance(parsed, dict)
        self.assertIn("records", parsed)

    def test_extract_records_tree_from_various(self):
        self.assertEqual(len(_extract_records_tree({"records": [{"x": 1}, {"x": 2}]})), 2)
        self.assertEqual(len(_extract_records_tree([{"records": [{"x": 1}]}, {"records": [{"x": 2}, {"x": 3}]}])), 3)
        self.assertEqual(len(_extract_records_tree({"x": 1})), 1)
        self.assertEqual(_extract_records_tree("nope"), [])

    def test_extract_messages_prefers_payload_then_fallback(self):
        body1 = json.dumps({"records": [{"payload": {"k": 1}}, {"payload": {"k": 2}}]})
        msgs1 = extract_messages_from_body(body1)
        self.assertEqual([json.loads(m)["k"] for m in msgs1], [1, 2])

        body2 = json.dumps({"records": [{"meta": {"a": 1}}, {"meta": {"a": 2}}]})
        msgs2 = extract_messages_from_body(body2)
        self.assertEqual([json.loads(m)["meta"]["a"] for m in msgs2], [1, 2])

    def test_extract_messages_plain_string_when_no_records(self):
        body = '"just a json string"'
        self.assertEqual(extract_messages_from_body(body), ["just a json string"])


class TestExplosionAndMapping(unittest.TestCase):
    def test_explode_event_pairs(self):
        event = {
            "Records": [
                {"messageId": "m1", "body": json.dumps({"records": [{"payload": {"id": 1}}, {"payload": {"id": 2}}]})},
                {"messageId": "m2", "body": json.dumps({"records": [{"payload": {"id": 3}}]})},
            ]
        }
        pairs = explode_sqs_event_to_messages(event)
        self.assertEqual([(sid, json.loads(b)["id"]) for sid, b in pairs], [("m1", 1), ("m1", 2), ("m2", 3)])

    def test_build_batch_item_failures_dedupes_by_source_id(self):
        flattened = [
            ("SRC1", json.dumps({"v": 1})),
            ("SRC1", json.dumps({"v": 2})),
            ("SRC2", json.dumps({"v": 3})),
        ]
        failed = [json.dumps({"v": 2}), json.dumps({"v": 3})]
        failures = build_batch_item_failures(flattened, failed)
        self.assertCountEqual(failures, [{"itemIdentifier": "SRC1"}, {"itemIdentifier": "SRC2"}])


if __name__ == "__main__":
    unittest.main()



##########################################################


# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest
from unittest.mock import patch

# import src.* (same path style as your current tests)
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

# Import after path setup so patch targets resolve
import handler  # noqa: E402


class TestLambdaHandlerOrchestration(unittest.TestCase):
    @patch.object(handler, "push_batch_to_sqs_concurrently")
    def test_lambda_handler_wiring_success(self, mock_pusher):
        # Arrange: two payloads from one incoming SQS record
        event = {
            "Records": [
                {"messageId": "SRC-1", "body": json.dumps({"records": [{"payload": {"a": 1}}, {"payload": {"a": 2}}]})}
            ]
        }
        mock_pusher.return_value = []  # no failures

        # Act
        resp = handler.lambda_handler(event, None)

        # Assert: pusher called once with the flattened bodies, no batch failures
        mock_pusher.assert_called_once()
        self.assertEqual(resp, {"batchItemFailures": []})

    @patch.object(handler, "push_batch_to_sqs_concurrently")
    def test_lambda_handler_maps_failures_back_to_source_ids(self, mock_pusher):
        # Arrange: three messages → mark the second body as failed
        body1 = json.dumps({"a": 1}, separators=(",", ":"), ensure_ascii=False)
        body2 = json.dumps({"a": 2}, separators=(",", ":"), ensure_ascii=False)
        body3 = json.dumps({"b": 3}, separators=(",", ":"), ensure_ascii=False)

        event = {
            "Records": [
                {"messageId": "SRC-1", "body": json.dumps({"records": [{"payload": {"a": 1}}, {"payload": {"a": 2}}]})},
                {"messageId": "SRC-2", "body": json.dumps({"records": [{"payload": {"b": 3}}]})},
            ]
        }

        mock_pusher.return_value = [body2, body3]  # these "bodies" failed to enqueue

        # Act
        resp = handler.lambda_handler(event, None)

        # Assert: one failure per source id that contained a failed body
        self.assertCountEqual(resp["batchItemFailures"], [
            {"itemIdentifier": "SRC-1"},
            {"itemIdentifier": "SRC-2"},
        ])


if __name__ == "__main__":
    unittest.main()


