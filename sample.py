# tests/utils/test_helpers.py
import json
import unittest

from helpers import (
    explode_sqs_event_to_payloads,
    _loads_multipass,
    _flatten_records,
    _to_json_string,
)


class TestHelpersFullCoverage(unittest.TestCase):
    # ---------------------------------------------------------------------
    # explode_sqs_event_to_payloads — primary paths
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
        event = {"Records": [{"messageId": "deep", "body": {"records": [[{"payload": {"z": 7}}], [[inner_list]]]}}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("deep", '{"z":7}'), ("deep", '{"z":9}')],
        )

    def test_records_present_but_nonjson_string_fallback_to_whole_body(self):
        event = {"Records": [{"messageId": "bad", "body": {"version": "1", "records": "not-json"}}]}
        self.assertEqual(
            explode_sqs_event_to_payloads(event),
            [("bad", '{"version":"1","records":"not-json"}')],
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

    def test_bytes_and_bytearray_bodies(self):
        container = {"records": [{"payload": {"x": 1}}, {"payload": {"x": 2}}]}
        data = json.dumps(container).encode()
        e1 = {"Records": [{"messageId": "B1", "body": data}]}
        e2 = {"Records": [{"messageId": "B2", "body": bytearray(data)}]}
        self.assertEqual(explode_sqs_event_to_payloads(e1), [("B1", '{"x":1}'), ("B1", '{"x":2}')])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [("B2", '{"x":1}'), ("B2", '{"x":2}')])

    def test_missing_messageid_missing_body_and_unrecognized_type(self):
        e1 = {"Records": [{"body": {"payload": {"a": 1}}}]}  # skip: no messageId
        e2 = {"Records": [{"messageId": "m1"}]}              # skip: no body
        e3 = {"Records": [{"messageId": "m2", "body": 12345}]}  # skip: unrecognized type
        self.assertEqual(explode_sqs_event_to_payloads(e1), [])
        self.assertEqual(explode_sqs_event_to_payloads(e2), [])
        self.assertEqual(explode_sqs_event_to_payloads(e3), [])

    def test_empty_inputs(self):
        self.assertEqual(explode_sqs_event_to_payloads({"Records": []}), [])
        self.assertEqual(explode_sqs_event_to_payloads({}), [])

    # ---------------------------------------------------------------------
    # _loads_multipass — all decoding branches
    # ---------------------------------------------------------------------

    def test_loads_multipass_bytes_dict_string_of_string_and_quoted(self):
        obj = {"a": 1}
        self.assertEqual(_loads_multipass(obj), obj)                     # already dict
        self.assertEqual(_loads_multipass(json.dumps(obj).encode()), obj)  # bytes
        s2 = json.dumps(json.dumps(obj))                                 # string of string
        self.assertEqual(_loads_multipass(s2), obj)
        quoted = '"{\\"b\\":2}"'                                         # quoted JSON
        self.assertEqual(_loads_multipass(quoted), {"b": 2})

    def test_loads_multipass_unicode_escape_success(self):
        raw = '{\\n  \\"obj\\": {\\"k\\": 1}\\n}'
        self.assertEqual(_loads_multipass(raw), {"obj": {"k": 1}})

    def test_loads_multipass_unicode_escape_transforms_nonjson(self):
        # contains \t → becomes a real tab after unicode_escape; still not JSON → returned as transformed string
        s = "text\\tstill-not-json"
        self.assertEqual(_loads_multipass(s), "text\tstill-not-json")

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
        self.assertEqual(_to_json_string({"a": 1}), '{"a":1}')  # dict
        already = '{"x":3}'                                     # already JSON string
        self.assertEqual(_to_json_string(already), already)
        self.assertEqual(_to_json_string(10), "10")             # scalar
        self.assertEqual(_to_json_string("hello"), '"hello"')   # non-JSON string gets quoted


if __name__ == "__main__":
    unittest.main()
