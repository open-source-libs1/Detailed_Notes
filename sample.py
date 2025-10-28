# tests/test_main.py
import json
import unittest
from unittest.mock import patch

from src.main import app, create_referral, update_referral, health_check, handle_not_found


class FakeEvent:
    """Minimal object with the bits our handlers read."""
    def __init__(self, body: dict | None, headers: dict | None = None):
        self.headers = headers or {"host": "api.example.com", "x-forwarded-proto": "https"}
        self._body = body

    @property
    def json_body(self):
        # Simulate Powertools behavior: if parsing failed, handlers' try/except should catch
        if self._body is None:
            raise ValueError("bad json")
        return self._body


def _set_current_event(body: dict | None, headers: dict | None = None):
    """Handlers read `app.current_event`; older Powertools also stores `_current_event`.
    Set both to be safe across versions.
    """
    fe = FakeEvent(body, headers=headers)
    setattr(app, "_current_event", fe)
    setattr(app, "current_event", fe)


class TestHandler(unittest.TestCase):
    # ------------------------ 201 CREATED ------------------------
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

    # ------------------------ 400s ------------------------
    def test_400_missing_body(self):
        # Forces the body-parse exception path -> 40001
        _set_current_event(None)
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)
        body = json.loads(res["body"])
        self.assertEqual(body["id"], 40001)

    def test_400_validation(self):
        # Invalid programCode (space) -> validation -> 40005 (or 40002 depending on pydantic message)
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
        self.assertIn(body["id"], (40005, 40002))  # accept either mapping

    # ------------------------ 500 ------------------------
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

    # ------------------------ other routes ------------------------
    def test_health(self):
        res = health_check()
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        self.assertEqual(body["status"], "healthy")

    def test_update_referral_204(self):
        _set_current_event({"x": 1})
        res = update_referral("abc")
        self.assertEqual(res["statusCode"], 204)
        self.assertEqual(res["body"], "")

    def test_not_found_404(self):
        res = handle_not_found({"path": "/nope"})
        self.assertEqual(res["statusCode"], 404)
        body = json.loads(res["body"])
        self.assertIn("Endpoint does not exist", body.get("error", ""))


