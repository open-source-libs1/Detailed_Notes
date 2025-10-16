


from __future__ import annotations
import json
from http import HTTPStatus
from typing import Any, Dict
from datetime import datetime, timezone

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import ALBResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

from .models.model_referral import (
    ReferralCreateRequest,
    ReferralCreateResponse,
    ErrorBody,
    map_validation_to_400xx,
)
from .database.db import create_referral_fulfillment

logger = Logger()
app = ALBResolver()

@app.get("/referrals/health")
def health() -> Dict[str, Any]:
    """Simple health endpoint for ALB checks."""
    return {"statusCode": 200, "body": json.dumps({"status": "healthy"})}

def _resp(status: int, body: Dict[str, Any], headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Small helper to standardize ALB-style responses."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **(headers or {})},
        "body": json.dumps(body),
    }

@app.post("/enterprise/referrals")
def create_referral() -> Dict[str, Any]:
    """
    Create a referral event.

    Changes per request:
    - We now *log* the would-be Location (for traceability) and a UTC timestamp,
      but we DO NOT return any Location header to the client.
    """
    # 1) Parse JSON body (ALBResolver exposes it via current_event)
    try:
        body = app.current_event.json_body or {}
    except Exception:
        return _resp(
            HTTPStatus.BAD_REQUEST,
            ErrorBody(id=40001, developerText="Missing required field in request (body)").model_dump(),
        )

    # 2) Validate input using Pydantic; map to acceptance 400xx codes
    try:
        req = ReferralCreateRequest.model_validate(body)
    except Exception as e:
        code, message = map_validation_to_400xx(e)
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=code, developerText=message).model_dump())

    # 3) Insert into DB
    try:
        rid = create_referral_fulfillment(req.model_dump())
    except Exception:
        logger.exception("db failure")
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorBody(id=50000, developerText="Internal Server Error").model_dump())

    # 4) Timestamp the creation and LOG the would-be Location (but do not send it back)
    created_at = datetime.now(timezone.utc).isoformat()
    host = app.current_event.headers.get("host", "")
    proto = app.current_event.headers.get("x-forwarded-proto", "https")
    path = f"/enterprise/referrals/{rid}"
    would_be_location = f"{proto}://{host}{path}" if host else path
    logger.info(
        f"referral created referralId={rid} createdAt={created_at} location={would_be_location}"
    )

    # 5) Return only the referralId with 201
    return _resp(HTTPStatus.CREATED, ReferralCreateResponse(referralId=rid).model_dump())
    # (Intentionally no 'Location' header.)

@app.not_found
def not_found(event) -> Dict[str, Any]:
    """Fallback for unmapped routes."""
    return _resp(HTTPStatus.NOT_FOUND, {"error": "Endpoint does not exist"})

@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: Dict[str, Any], context: LambdaContext):
    """Delegates to ALBResolver; kept thin for clarity and testability."""
    return app.resolve(event, context)






###################



import json
import unittest
from unittest.mock import patch

from src.main import app, create_referral, health, not_found, lambda_handler

class FakeEvent:
    """Minimal shim to emulate ALBResolver's current_event artifact."""
    def __init__(self, body: dict | None, headers=None):
        self.headers = headers or {"host": "api.example.com", "x-forwarded-proto": "https"}
        self._body = body
    @property
    def json_body(self):
        if self._body is None:
            # Triggers our 40001 path in main.py
            raise ValueError("invalid json")
        return self._body

class TestMain(unittest.TestCase):
    # ---- Health & Not Found --------------------------------------------------

    def test_health(self):
        res = health()
        self.assertEqual(res["statusCode"], 200)
        payload = json.loads(res["body"])
        self.assertEqual(payload["status"], "healthy")

    def test_not_found(self):
        res = not_found({"x": 1})
        self.assertEqual(res["statusCode"], 404)

    # ---- create_referral paths ----------------------------------------------

    def _set_event(self, body):
        # ALBResolver stores the "current_event" on the resolver instance.
        app._current_event = FakeEvent(body)  # type: ignore[attr-defined]

    @patch("src.main.create_referral_fulfillment", return_value="RID123")
    @patch("src.main.logger.info")
    def test_create_referral_201_no_location_header(self, log_info, _db):
        body = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "SOR-X",
            "referralReferenceKeys": [],
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }
        self._set_event(body)
        res = create_referral()
        # Assert success
        self.assertEqual(res["statusCode"], 201)
        payload = json.loads(res["body"])
        self.assertEqual(payload["referralId"], "RID123")
        # Assert we did NOT send a Location header
        self.assertNotIn("Location", res["headers"])
        # Ensure we logged the creation with a 'referral created' message
        log_calls = " ".join(str(c.args[0]) for c in log_info.mock_calls if c.args)
        self.assertIn("referral created", log_calls)
        self.assertIn("RID123", log_calls)

    def test_create_referral_400_missing_body(self):
        # json_body property will raise —> 40001
        app._current_event = FakeEvent(None)  # type: ignore
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)
        body = json.loads(res["body"])
        self.assertEqual(body["id"], 40001)

    def test_create_referral_400_validation(self):
        # Missing a bunch + invalid programCode triggers validation mapping
        self._set_event({"programCode": "BAD SPACE"})
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)
        body = json.loads(res["body"])
        self.assertIn(body["id"], (40001, 40002, 40003, 40004, 40005))

    @patch("src.main.create_referral_fulfillment", side_effect=RuntimeError("db down"))
    def test_create_referral_500_db_error(self, _db):
        body = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "SOR",
            "referralReferenceKeys": [],
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }
        self._set_event(body)
        res = create_referral()
        self.assertEqual(res["statusCode"], 500)

    # ---- lambda_handler pass-through ----------------------------------------

    @patch("src.main.app.resolve", return_value={"statusCode": 204, "body": ""})
    def test_lambda_handler(self, resolve_mock):
        res = lambda_handler({"any": "event"}, None)  # context not needed
        self.assertEqual(res["statusCode"], 204)
        resolve_mock.assert_called_once()



