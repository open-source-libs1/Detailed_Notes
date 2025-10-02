import json
import logging

logger = logging.getLogger(__name__)

def explode_sqs_event_to_payloads(event):
    """Extracts payloads from a well-formed AWS SQS event.

    Each record inside the SQS `event['Records']` contains a `body` field
    that is a serialized JSON string. Each body includes a `records` list,
    and each record has a `payload` string that is itself a JSON string.
    This function flattens all payloads into a list of `(message_id, payload_json)` tuples.

    Args:
        event (dict): The SQS event object received by the Lambda handler.

    Returns:
        list[tuple[str, str]]: List of (message_id, payload_json_string).

    Example:
        >>> event = {
        ...   "Records": [
        ...     {
        ...       "messageId": "A",
        ...       "body": '{"records":[{"payload":"{\\"id\\":1}"},{"payload":"{\\"id\\":2}"}]}'
        ...     }
        ...   ]
        ... }
        >>> explode_sqs_event_to_payloads(event)
        [('A', '{"id":1}'), ('A', '{"id":2}')]
    """
    flattened = []

    for record in event.get("Records", []):
        message_id = record.get("messageId")
        body = record.get("body")

        if not body:
            logger.warning("Skipping record with empty body: %s", message_id)
            continue

        try:
            body_json = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse body for message %s: %s", message_id, e)
            continue

        for inner_record in body_json.get("records", []):
            payload_str = inner_record.get("payload")
            if not payload_str:
                logger.warning("Missing payload in record: %s", message_id)
                continue

            try:
                # Decode the escaped payload JSON string
                payload = json.loads(payload_str)
                payload_json = json.dumps(payload)
                flattened.append((message_id, payload_json))
            except json.JSONDecodeError as e:
                logger.error("Failed to decode payload for message %s: %s", message_id, e)

    return flattened


##############################


import unittest
from src.utils.helpers import explode_sqs_event_to_payloads

class TestHelpersSimplified(unittest.TestCase):
    """Covers all typical and edge cases for explode_sqs_event_to_payloads."""

    def test_single_payload(self):
        event = {
            "Records": [
                {
                    "messageId": "M1",
                    "body": '{"records":[{"payload":"{\\"id\\":1}"}]}'
                }
            ]
        }
        expected = [("M1", '{"id": 1}')]
        self.assertEqual(explode_sqs_event_to_payloads(event), expected)

    def test_multiple_payloads(self):
        event = {
            "Records": [
                {
                    "messageId": "M2",
                    "body": '{"records":[{"payload":"{\\"x\\":1}"},{"payload":"{\\"y\\":2}"}]}'
                }
            ]
        }
        expected = [("M2", '{"x": 1}'), ("M2", '{"y": 2}')]
        self.assertEqual(explode_sqs_event_to_payloads(event), expected)

    def test_empty_records(self):
        event = {"Records": []}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_missing_body(self):
        event = {"Records": [{"messageId": "X"}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_invalid_json_body(self):
        event = {"Records": [{"messageId": "Y", "body": "{invalid-json}"}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_missing_payload_field(self):
        event = {
            "Records": [
                {
                    "messageId": "Z",
                    "body": '{"records":[{"meta":{"ref":"1"}}]}'
                }
            ]
        }
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_invalid_payload_json(self):
        event = {
            "Records": [
                {
                    "messageId": "E1",
                    "body": '{"records":[{"payload":"{invalid-json}"}]}'
                }
            ]
        }
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_multiple_records_in_multiple_messages(self):
        event = {
            "Records": [
                {
                    "messageId": "A",
                    "body": '{"records":[{"payload":"{\\"a\\":1}"}]}'
                },
                {
                    "messageId": "B",
                    "body": '{"records":[{"payload":"{\\"b\\":2}"},{"payload":"{\\"c\\":3}"}]}'
                }
            ]
        }
        expected = [
            ("A", '{"a": 1}'),
            ("B", '{"b": 2}'),
            ("B", '{"c": 3}')
        ]
        self.assertEqual(explode_sqs_event_to_payloads(event), expected)



