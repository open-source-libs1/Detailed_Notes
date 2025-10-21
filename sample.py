# src/models/model_referral.py

from pydantic import BaseModel, Field, ValidationError, field_validator
import re
from typing import List

class BadRequest(ValueError):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)

def map_validation_to_400xx(exc: Exception) -> tuple[int, str]:
    """
    Priority:
      1) BadRequest -> explicit 400xx (rare if raised outside Pydantic)
      2) Pydantic missing field -> 40001
      3) Recognize our business messages -> 40003/40004/40005
      4) Otherwise -> 40002
    """
    if isinstance(exc, BadRequest):
        return exc.code, str(exc)

    if isinstance(exc, ValidationError):
        errors = exc.errors()

        # Missing required field (pydantic v2 type is "missing")
        for err in errors:
            etype = (err.get("type") or "").lower()
            if etype == "missing" or etype.endswith("missing"):
                loc = ".".join(str(p) for p in err.get("loc", [])) or "field"
                return (40001, f"Missing required field in request ({loc})")

        # Map our business messages back to 400xx
        for err in errors:
            msg = (err.get("msg") or "").strip()
            if "Invalid account key type" in msg:
                return (40004, "Invalid account key type")
            if "Invalid referral code format" in msg:
                return (40003, "Invalid referral code format")
            if "Invalid referral program code" in msg:
                return (40005, "Invalid referral program code")

        # Fallback
        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", [])) or "field"
            return (40002, f"Invalid value for field {loc}")

    return (40002, "Invalid value")

# --- Models (unchanged) ---
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



#######################################


# tests/test_utils.py

import os
import unittest
from unittest.mock import patch
from src.utils.database_utils import get_db_params

BASE_ENV = {
    "DB_USERNAME": "u",
    "DB_PASSWORD": "p",
    "DB_NAME": "n",
    "DB_HOST": "h",
    "DB_PORT": "5432",
}

class TestDBUtils(unittest.TestCase):
    @patch.dict(os.environ, BASE_ENV, clear=True)
    def test_ok(self):
        db_name, db_user, db_password, db_host, db_port = get_db_params()
        self.assertEqual((db_name, db_user, db_password, db_host, db_port),
                         ("n", "u", "p", "h", "5432"))

    @patch.dict(os.environ, {k: v for k, v in BASE_ENV.items() if k != "DB_USERNAME"}, clear=True)
    def test_missing_user(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_user", str(ctx.exception))

    @patch.dict(os.environ, {k: v for k, v in BASE_ENV.items() if k != "DB_PASSWORD"}, clear=True)
    def test_missing_password(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_password", str(ctx.exception))

    @patch.dict(os.environ, {k: v for k, v in BASE_ENV.items() if k != "DB_NAME"}, clear=True)
    def test_missing_name(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_name", str(ctx.exception))

    @patch.dict(os.environ, {k: v for k, v in BASE_ENV.items() if k != "DB_HOST"}, clear=True)
    def test_missing_host(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_host", str(ctx.exception))

    @patch.dict(os.environ, {k: v for k, v in BASE_ENV.items() if k != "DB_PORT"}, clear=True)
    def test_missing_port(self):
        with self.assertRaises(RuntimeError) as ctx:
            get_db_params()
        self.assertIn("db_port", str(ctx.exception))
