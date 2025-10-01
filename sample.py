import json
import unittest
from helpers import (
    explode_sqs_event_to_payloads,
    _loads_multipass,
    _flatten_records,
    _to_json_string,
)


class TestHelpersFullCoverage(unittest.TestCase):

    # -------------------------------------------------------------------------
    # explode_sqs_event_to_payloads
    # -------------------------------------------------------------------------

    def test_multiple_payloads_in_single_record(self):
        """Covers multiple payloads in records list."""
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

    def test_messageid_lowercase_and_records_as_dict(self):
        """Covers lowercase messageid + records as dict instead of list."""
        event = {"Records": [{"messageid": "x", "body": {"records": {"payload": {"x": 1}}}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("x", '{"x":1}')])

    def test_body_dict_with_payload_that_has_nested_records(self):
        """Covers payload → dict containing its own 'records' key."""
        inner = {"records": [{"payload": {"q": 5}}, {"payload": {"q": 6}}]}
        event = {"Records": [{"messageId": "nested", "body": {"payload": json.dumps(inner)}}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("nested", '{"q":5}'), ("nested", '{"q":6}')],
        )

    def test_records_is_nonjson_string_fallback_to_entire_body(self):
        """Covers fallback where records value is non-JSON string."""
        event = {"Records": [{"messageId": "bad", "body": {"records": "abc", "x": 2}}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("bad", '{"records":"abc","x":2}')],
        )

    def test_body_is_string_that_decodes_to_records_json(self):
        """Covers body string decoding into container with records."""
        recs = json.dumps([{"payload": {"v": 1}}, {"payload": {"v": 2}}])
        event = {"Records": [{"messageId": "stringy", "body": json.dumps({"records": recs})}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("stringy", '{"v":1}'), ("stringy", '{"v":2}')],
        )

    def test_body_is_string_with_double_escaped_backslashes(self):
        """Covers CloudWatch-style body with \\n and escaped quotes."""
        raw = '{\\n\\"records\\":[{\\n\\"payload\\":{\\"a\\":1}},{\\n\\"payload\\":{\\"a\\":2}}]}'
        event = {"Records": [{"messageId": "E", "body": raw}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("E", '{"a":1}'), ("E", '{"a":2}')],
        )

    def test_deeply_nested_records_lists(self):
        """Covers deeply nested list-of-lists inside records."""
        inner_json = json.dumps([{"payload": {"deep": 1}}, {"payload": {"deep": 2}}])
        event = {"Records": [{"messageId": "deep", "body": {"records": [[[[inner_json]]]]}}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("deep", '{"deep":1}'), ("deep", '{"deep":2}')],
        )

    def test_body_is_dict_without_records_or_payload(self):
        """Covers dict body with no records/payload → treated as payload."""
        event = {"Records": [{"messageId": "plain", "body": {"x": True}}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("plain", '{"x":true}')])

    def test_missing_messageid_and_missing_body(self):
        """Covers missing messageId and missing body."""
        e1 = {"Records": [{"body": {"payload": {"a": 1}}}]}
        e2 = {"Records": [{"messageId": "m1"}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [])

    def test_unrecognized_body_type_int(self):
        """Covers unrecognized body type (int)."""
        event = {"Records": [{"messageId": "Z", "body": 12345}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [])

    def test_empty_records_list_and_empty_event(self):
        """Covers empty input variants."""
        self.assertEqual(explode_sqs_event_to_payloads({"Records": []}), [])
        self.assertEqual(explode_sqs_event_to_payloads({}), [])

    def test_bytes_and_bytearray_bodies(self):
        """Covers bytes and bytearray handling."""
        container = {"records": [{"payload": {"x": 1}}, {"payload": {"x": 2}}]}
        data = json.dumps(container).encode()
        e1 = {"Records": [{"messageId": "B1", "body": data}]}
        e2 = {"Records": [{"messageId": "B2", "body": bytearray(data)}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [("B1", '{"x":1}'), ("B1", '{"x":2}')])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [("B2", '{"x":1}'), ("B2", '{"x":2}')])

    # -------------------------------------------------------------------------
    # _loads_multipass
    # -------------------------------------------------------------------------

    def test_loads_multipass_dict_bytes_and_multiple_peels(self):
        """Covers dict input, bytes input, quoted JSON, and nested JSON string."""
        obj = {"a": 1}
        s1 = json.dumps(obj)
        s2 = json.dumps(s1)
        self.assertEqual(_loads_multipass(obj), obj)
        self.assertEqual(_loads_multipass(s2), obj)
        b = json.dumps(obj).encode()
        self.assertEqual(_loads_multipass(b), obj)
        quoted = '"{\\"b\\":2}"'
        self.assertEqual(_loads_multipass(quoted), {"b": 2})

    def test_loads_multipass_unicode_escape_then_json_fails_and_returns_original(self):
        """Covers unicode_escape path where decoding fails to parse as JSON."""
        s = "text\\tstill-not-json"
        result = _loads_multipass(s)
        # it decodes \t → tab but still not JSON
        self.assertEqual(result, "text\tstill-not-json")

    def test_loads_multipass_unicode_escape_success_then_repeats(self):
        """Covers repeated peeling until inner JSON reached."""
        raw = '"{\\n  \\"obj\\": {\\"k\\": 1}\\n}"'
        out = _loads_multipass(raw)
        self.assertEqual(out, {"obj": {"k": 1}})

    def test_loads_multipass_not_json_string_returned_unchanged(self):
        """Covers strings that are not JSON-looking."""
        val = "not json"
        self.assertEqual(_loads_multipass(val), "not json")

    # -------------------------------------------------------------------------
    # _flatten_records
    # -------------------------------------------------------------------------

    def test_flatten_records_with_list_dict_str(self):
        """Covers list of dicts and JSON strings inside list."""
        inner = json.dumps([{"payload": 9}])
        obj = [{"payload": 5}, [json.dumps({"payload": 6})], inner]
        out = list(_flatten_records(obj))
        vals = [d["payload"] for d in out]
        self.assertIn(5, vals)
        self.assertIn(6, vals)
        self.assertIn(9, vals)

    def test_flatten_records_with_non_json_string(self):
        """Covers string that is not JSON."""
        out = list(_flatten_records(["abc"]))
        self.assertEqual(out, [])

    # -------------------------------------------------------------------------
    # _to_json_string
    # -------------------------------------------------------------------------

    def test_to_json_string_various_inputs(self):
        """Covers dict, already-json-string, scalar, and non-json string."""
        self.assertEqual(_to_json_string({"a": 1}), '{"a":1}')
        j = '{"b":2}'
        self.assertEqual(_to_json_string(j), j)
        self.assertEqual(_to_json_string(10), "10")
        self.assertEqual(_to_json_string("hello"), '"hello"')


if __name__ == "__main__":
    unittest.main()
