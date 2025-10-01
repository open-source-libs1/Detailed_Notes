
# tests/utils/test_helpers.py
import json
import unittest
from helpers import (
    explode_sqs_event_to_payloads,
    _loads_multipass,
    _flatten_records,
    _to_json_string,
)

class TestExplodeSQSEvent(unittest.TestCase):

    # ---- Core event extraction paths ----
    def test_multiple_payloads_per_record_dict_body(self):
        event = {
            "Records": [
                {"messageId": "A",
                 "body": {"version": "1", "records": [
                     {"payload": {"id": 1}},
                     {"payload": {"id": 2}},
                 ]}},
            ]
        }
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("A", '{"id":1}'), ("A", '{"id":2}')])

    def test_records_as_string_needing_extra_peel(self):
        records_str = json.dumps([{"payload": {"v": 10}}, {"payload": {"v": 20}}])
        event = {"Records": [{"messageId": "X", "body": {"records": records_str}}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("X", '{"v":10}'), ("X", '{"v":20}')])

    def test_payload_contains_nested_records(self):
        inner = {"records": [{"payload": {"x": 1}}, {"payload": {"x": 2}}]}
        event = {"Records": [{"messageId": "P", "body": {"payload": json.dumps(inner)}}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("P", '{"x":1}'), ("P", '{"x":2}')])

    def test_list_of_lists_double_escaped_string(self):
        payload = {"meta": {"ref": "r"}, "payload": {"a": 5}}
        container = {"records": [[payload, payload]]}
        twice = json.dumps(json.dumps(container))
        event = {"Records": [{"messageId": "Y", "body": twice}]}
        out = explode_sqs_event_to_payloads(event)
        self.assertEqual(out, [("Y", '{"a":5}'), ("Y", '{"a":5}')])

    def test_bytes_and_bytearray_inputs(self):
        container = {"records": [{"payload": {"b": 1}}, {"payload": {"b": 2}}]}
        data = json.dumps(container).encode("utf-8")
        e1 = {"Records": [{"messageId": "B1", "body": data}]}
        e2 = {"Records": [{"messageId": "B2", "body": {"payload": data}}]}
        e3 = {"Records": [{"messageId": "B3", "body": bytearray(data)}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1),
                         [("B1", '{"b":1}'), ("B1", '{"b":2}')])
        self.assertEqual(explode_sqs_event_to_payloads(e2),
                         [("B2", '{"b":1}'), ("B2", '{"b":2}')])
        self.assertEqual(explode_sqs_event_to_payloads(e3),
                         [("B3", '{"b":1}'), ("B3", '{"b":2}')])

    def test_body_is_dict_without_records_or_payload(self):
        e = {"Records": [{"messageId": "M", "body": {"simple": True}}]}
        self.assertEqual(explode_sqs_event_to_payloads(e), [("M", '{"simple":true}')])

    def test_unrecognized_body_shape_int_and_missing_keys(self):
        e1 = {"Records": [{"messageId": "A", "body": 123}]}
        e2 = {"Records": [{"body": {"payload": {"k": 1}}}]}
        e3 = {"Records": [{"messageId": "B"}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [])
        self.assertEqual(explode_sqs_event_to_payloads(e3), [])

    def test_body_is_string_payload_json(self):
        body = '{"id":42,"ok":true}'
        event = {"Records": [{"messageId": "Z", "body": body}]}
        self.assertEqual(explode_sqs_event_to_payloads(event), [("Z", body)])

    def test_double_escaped_newline_and_quote(self):
        # simulates logs with literal \\n and \"
        raw = '{\\n\\"records\\":[{\\n\\"payload\\":{\\"p\\":1}}' \
              ',{\\n\\"payload\\":{\\"p\\":2}}]}'
        event = {"Records": [{"messageId": "E", "body": raw}]}
        self.assertEqual(explode_sqs_event_to_payloads(event),
                         [("E", '{"p":1}'), ("E", '{"p":2}')])

    # ---- internal helper tests ----
    def test_loads_multipass_plain_dict_and_double_encoded(self):
        d = {"a": 1}
        s1 = json.dumps(d)
        s2 = json.dumps(s1)
        self.assertEqual(_loads_multipass(d), d)
        self.assertEqual(_loads_multipass(s2), d)

    def test_loads_multipass_single_quoted_and_unicode_escape(self):
        # quoted JSON string
        quoted = '"{\\"x\\":1}"'
        self.assertEqual(_loads_multipass(quoted), {"x": 1})
        # non-JSON with backslashes → returned unchanged
        invalid = 'text\\notjson'
        self.assertEqual(_loads_multipass(invalid), 'text\\notjson')

    def test_loads_multipass_bytes_and_non_json(self):
        b = json.dumps({"k": 2}).encode()
        self.assertEqual(_loads_multipass(b), {"k": 2})
        self.assertEqual(_loads_multipass("not json"), "not json")

    def test_flatten_records_various_structures(self):
        d1 = {"payload": 1}
        d2 = [{"payload": 2}, [{"payload": 3}]]
        s = json.dumps([{"payload": 4}])
        out = list(_flatten_records([d1, d2, s]))
        vals = [x["payload"] for x in out]
        self.assertIn(1, vals)
        self.assertIn(2, vals)
        self.assertIn(3, vals)
        self.assertIn(4, vals)

    def test_to_json_string_all_paths(self):
        self.assertEqual(_to_json_string({"a": 1}), '{"a":1}')
        j = '{"b":2}'
        self.assertEqual(_to_json_string(j), j)
        self.assertEqual(_to_json_string(5), "5")

if __name__ == "__main__":
    unittest.main()
