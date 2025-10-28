# tests/test_main.py
import json
import unittest
from unittest.mock import patch

from src.main import app, create_referral, update_referral, health_check, handle_not_found


class FakeEvent:
    """Minimal object that looks like ALBResolver's current_event for our handlers."""
    def __init__(self, body: dict | None, headers: dict | None = None):
        self.headers = headers or {"host": "api.example.com", "x-forwarded-proto": "https"}
        self._body = body

    @property
    def json_body(self):
        # Simulate "bad JSON" path in main.py when parsing fails
        if self._body is None:
            raise ValueError("bad json")
        return self._body


class TestHandler(unittest.TestCase):
    def set_event(self, body: dict | None, headers: dict | None = None):
        # Powertools' resolver stores the event on a private field the handlers read from.
        app._current_event = FakeEvent(body, headers=headers)

    # ---- happy path ---------------------------------------------------------
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
        self.set_event(body)
        res = create_referral()
        self.assertEqual(res["statusCode"], 201)
        payload = json.loads(res["body"])
        self.assertEqual(payload["referralId"], "123")
        # Note: current main.py does NOT return a Location header; don't assert it.

    # ---- 400 cases ----------------------------------------------------------
    def test_400_missing_body(self):
        # json parsing raises -> 40001 path
        app._current_event = FakeEvent(None)
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)
        payload = json.loads(res["body"])
        self.assertEqual(payload["id"], 40001)

    def test_400_validation(self):
        # Invalid programCode pattern -> validator raises BadRequest(40005, ...)
        self.set_event({
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S1",
            "referralCode": "REF_001",
            "programCode": "BAD SPACE",  # invalid by regex
        })
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)
        payload = json.loads(res["body"])
        # Error id should map to program code validator
        self.assertIn(payload["id"], (40002, 40005))

    # ---- 500 case -----------------------------------------------------------
    @patch("src.main.create_referral_fulfillment", side_effect=RuntimeError("db down"))
    def test_500_db(self, _db):
        body = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S1",
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }
        self.set_event(body)
        res = create_referral()
        self.assertEqual(res["statusCode"], 500)
        payload = json.loads(res["body"])
        self.assertEqual(payload["id"], 50000)

    # ---- other routes -------------------------------------------------------
    def test_health(self):
        res = health_check()
        self.assertEqual(res["statusCode"], 200)
        payload = json.loads(res["body"])
        self.assertEqual(payload["status"], "healthy")

    def test_update_referral_204(self):
        self.set_event({"x": 1})
        res = update_referral("abc")
        self.assertEqual(res["statusCode"], 204)
        self.assertEqual(res["body"], "")

    def test_not_found_404(self):
        res = handle_not_found({"path": "/nope"})
        self.assertEqual(res["statusCode"], 404)
        payload = json.loads(res["body"])
        self.assertIn("Endpoint does not exist", payload.get("error", ""))


if __name__ == "__main__":
    unittest.main()
