import json
import os
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

# Make "src/" importable when running tests directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.main import app, create_referral, update_referral, health_check, handle_not_found  # noqa: E402

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

EVENT_UUID = "924c2586-7958-4fce-8296-53c73076019e"
REQUEST_ID = "req-123"


class FakeEvent:
    """Minimal object with the bits our handlers read."""
    def __init__(self, body: dict | None, headers: dict | None = None, request_id: str = REQUEST_ID):
        self.headers = headers or {"host": "api.example.com", "x-forwarded-proto": "https"}
        self._body = body
        self.request_context = {"requestId": request_id}

    @property
    def json_body(self):
        if self._body is None:
            raise ValueError("bad json")
        return self._body


def _set_current_event(
    body: dict | None,
    headers: dict | None = None,
    request_id: str = REQUEST_ID,
    event_uuid: str = EVENT_UUID,
) -> None:
    fe = FakeEvent(body, headers=headers, request_id=request_id)
    setattr(app, "_current_event", fe)
    setattr(app, "current_event", fe)
    setattr(app, "lambda_context", SimpleNamespace(aws_request_id=event_uuid))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHandler(unittest.TestCase):
    # ------------------------- 201 CREATED -------------------------
    @patch("src.main.create_referral_fulfillment", return_value="123")
    def test_201(self, _db):
        body = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S1",
            "referralReferenceKeys": [],
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }

        _set_current_event(body)
        res = create_referral()

        self.assertEqual(res["statusCode"], 201)
        payload = json.loads(res["body"])
        self.assertEqual(payload["referralId"], "123")

        # App passes (payload, correlation_id, event_id)
        args, _ = _db.call_args
        self.assertIsInstance(args[0], dict)
        self.assertEqual(args[1], REQUEST_ID)   # correlation_id
        self.assertEqual(args[2], EVENT_UUID)   # event_id

    # ----------------------------- 400s ----------------------------
    def test_400_missing_body(self):
        _set_current_event(None)
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)
        body = json.loads(res["body"])
        self.assertEqual(body["id"], 40001)

    def test_400_validation(self):
        _set_current_event({
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S1",
            "referralCode": "REF_001",
            "programCode": "BAD SPACE",
        })
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)
        body = json.loads(res["body"])
        self.assertIn(body["id"], (40005, 40002))

    # ----------------------------- 500 -----------------------------
    @patch("src.main.create_referral_fulfillment", side_effect=RuntimeError("db down"))
    def test_500_db(self, _db):
        good = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S1",
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }
        _set_current_event(good)
        res = create_referral()
        self.assertEqual(res["statusCode"], 500)
        body = json.loads(res["body"])
        self.assertEqual(body["id"], 50000)

    # ------------------------- other routes ------------------------
    def test_health(self):
        res = health_check()
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["status"], "healthy")

    def test_update_referral_204(self):
        _set_current_event({"x": 1})
        res = update_referral("abc")
        self.assertEqual(res["statusCode"], 204)
        # Some implementations return "" for 204, others "{}"
        self.assertIn(res["body"], ("", "{}"))

    def test_not_found_404(self):
        # handle_not_found now expects an arg; pass a dummy event
        res = handle_not_found({})
        self.assertEqual(res["statusCode"], 404)
        json.loads(res["body"])  # valid JSON

if __name__ == "__main__":
    unittest.main(verbosity=2)
