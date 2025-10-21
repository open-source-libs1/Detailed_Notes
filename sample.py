from __future__ import annotations
import re
from typing import List
from pydantic import BaseModel, Field, ValidationError, field_validator

class BadRequest(ValueError):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)

def map_validation_to_400xx(exc: Exception) -> tuple[int, str]:
    """
    Priority:
      1) BadRequest -> explicit 400xx
      2) Pydantic missing field -> 40001
      3) Recognize business messages -> 40003/40004/40005
      4) Otherwise -> 40002
    """
    if isinstance(exc, BadRequest):
        return exc.code, str(exc)

    if isinstance(exc, ValidationError):
        errors = exc.errors()
        for err in errors:
            etype = (err.get("type") or "").lower()
            if etype == "missing" or etype.endswith("missing"):
                loc = ".".join(str(p) for p in err.get("loc", [])) or "field"
                return (40001, f"Missing required field in request ({loc})")

        for err in errors:
            msg = (err.get("msg") or "").strip()
            if "Invalid account key type" in msg:
                return (40004, "Invalid account key type")
            if "Invalid referral code format" in msg:
                return (40003, "Invalid referral code format")
            if "Invalid referral program code" in msg:
                return (40005, "Invalid referral program code")

        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", [])) or "field"
            return (40002, f"Invalid value for field {loc}")

    return (40002, "Invalid value")

class ReferralReferenceKey(BaseModel):
    referralReferenceKeyName: str = Field(..., min_length=1, max_length=64)
    referralReferenceKeyValue: str = Field(..., min_length=1, max_length=128)

class ReferralCreateRequest(BaseModel):
    prospectAccountKey: str = Field(..., min_length=1, max_length=64)
    prospectAccountKeyType: str = Field(..., min_length=1, max_length=64)
    sorId: str = Field(..., min_length=1, max_length=64)
    referralReferenceKeys: List[ReferralReferenceKey] = Field(default_factory=list)
    programCode: str = Field(..., min_length=1, max_length=64)
    referralCode: str = Field(..., min_length=1, max_length=64)

    @field_validator("prospectAccountKeyType")
    @classmethod
    def _v_account_key_type(cls, v: str) -> str:
        if v not in {"CARD_ACCOUNT_ID"}:
            raise BadRequest(40004, "Invalid account key type")
        return v

    @field_validator("referralCode")
    @classmethod
    def _v_referral_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v):
            raise BadRequest(40003, "Invalid referral code format")
        return v

    @field_validator("programCode")
    @classmethod
    def _v_program_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v):
            raise BadRequest(40005, "Invalid referral program code")
        return v

class ReferralCreateResponse(BaseModel):
    referralId: str

class ErrorBody(BaseModel):
    id: int
    developerText: str




###############################



from __future__ import annotations
import json
from http import HTTPStatus
from typing import Any, Dict

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
    return {"statusCode": 200, "body": json.dumps({"status": "healthy"})}

def _resp(status: int, body: Dict[str, Any], headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **(headers or {})},
        "body": json.dumps(body),
    }

def _get_json_body() -> Dict[str, Any]:
    """
    Work with both runtime and tests:
      - prefer app.current_event; fallback to app._current_event
      - support property or callable .json_body
    """
    ev = getattr(app, "current_event", None) or getattr(app, "_current_event", None)
    if ev is None:
        raise ValueError("no event")
    jb = getattr(ev, "json_body", None)
    if jb is None:
        raise ValueError("missing body")
    return jb() if callable(jb) else (jb or {})

@app.post("/enterprise/referrals")
async def create_referral() -> Dict[str, Any]:
    # 1) body
    try:
        body = _get_json_body()
    except Exception:
        return _resp(
            HTTPStatus.BAD_REQUEST,
            ErrorBody(id=40001, developerText="Missing required field in request (body)").model_dump()
        )

    # 2) validate (pydantic v2)
    try:
        req = ReferralCreateRequest.model_validate(body)
    except Exception as e:
        code, message = map_validation_to_400xx(e)
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=code, developerText=message).model_dump())

    # 3) db
    try:
        rid = await create_referral_fulfillment(req.model_dump())
    except Exception:
        logger.exception("db failure")
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorBody(id=50000, developerText="Internal Server Error").model_dump())

    # 4) created
    host = getattr(getattr(app, "current_event", None) or getattr(app, "_current_event", None), "headers", {}) or {}
    proto = host.get("x-forwarded-proto", "https")
    domain = host.get("host", "")
    location = f"{proto}://{domain}/enterprise/referrals/{rid}" if domain else f"/enterprise/referrals/{rid}"
    return _resp(HTTPStatus.CREATED, ReferralCreateResponse(referralId=rid).model_dump(), headers={"Location": location})

@app.not_found
def not_found(event) -> Dict[str, Any]:
    return _resp(HTTPStatus.NOT_FOUND, {"error": "Endpoint does not exist"})

@logger.inject_lambda_context(log_event=True)
async def lambda_handler(event: Dict[str, Any], context: LambdaContext):
    return await app.resolve(event, context)




#######################################



import os
import unittest
from unittest.mock import patch
from src.utils.database_utils import get_db_params

BASE = {
    "DB_USERNAME": "u",
    "DB_PASSWORD": "p",
    "DB_NAME": "n",
    "DB_HOST": "h",
    "DB_PORT": "5432",
}

class TestDBUtils(unittest.TestCase):
    @patch.dict(os.environ, BASE, clear=True)
    def test_ok(self):
        self.assertEqual(get_db_params(), ("n","u","p","h","5432"))

    @patch.dict(os.environ, {k:v for k,v in BASE.items() if k!="DB_USERNAME"}, clear=True)
    def test_missing_user(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_user", str(ctx.exception))

    @patch.dict(os.environ, {k:v for k,v in BASE.items() if k!="DB_PASSWORD"}, clear=True)
    def test_missing_pw(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_password", str(ctx.exception))

    @patch.dict(os.environ, {k:v for k,v in BASE.items() if k!="DB_NAME"}, clear=True)
    def test_missing_name(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_name", str(ctx.exception))

    @patch.dict(os.environ, {k:v for k,v in BASE.items() if k!="DB_HOST"}, clear=True)
    def test_missing_host(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_host", str(ctx.exception))

    @patch.dict(os.environ, {k:v for k,v in BASE.items() if k!="DB_PORT"}, clear=True)
    def test_missing_port(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_port", str(ctx.exception))




#########################################


from src.main import health, not_found

async def test_health_direct():
    res = health()
    assert res["statusCode"] == 200

async def test_not_found_direct():
    res = not_found({})
    assert res["statusCode"] == 404
