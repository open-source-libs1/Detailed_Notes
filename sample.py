

src/
  main.py
  models/
    __init__.py
    model_referral.py
  database/
    __init__.py
    db.py
  utils/
    __init__.py
    database_utils.py
tests/
  test_main.py
  test_models.py
  test_utils.py
  test_db.py
infra/
  cloudformation.yaml



########################


from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field, ValidationError, validator
import re

# -- Error helpers & mapping kept here so models are self-contained --

class BadRequest(ValueError):
    """Encodes specific 400xx codes from business validation."""
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)

def map_validation_to_400xx(exc: Exception) -> tuple[int, str]:
    """
    Priority:
      1) BadRequest -> explicit 400xx
      2) Pydantic missing field -> 40001
      3) Any other validation error -> 40002
    """
    if isinstance(exc, BadRequest):
        return exc.code, str(exc)

    if isinstance(exc, ValidationError):
        for err in exc.errors():
            if err.get("type") == "missing":
                loc = ".".join(str(p) for p in err.get("loc", [])) or "field"
                return 40001, f"Missing required field in request ({loc})"
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", [])) or "field"
        return 40002, f"Invalid value for field {loc}"

    return 40002, "Invalid value"

# -- Request/Response models --

class ReferralReferenceKey(BaseModel):
    referralReferenceKeyName: str = Field(..., min_length=1, max_length=64)
    referralReferenceKeyValue: str = Field(..., min_length=1, max_length=128)

class ReferralCreateRequest(BaseModel):
    prospectAccountKey: str = Field(..., min_length=1, max_length=64)
    prospectAccountKeyType: str = Field(..., min_length=1, max_length=64)  # validated
    sorId: str = Field(..., min_length=1, max_length=64)
    referralReferenceKeys: List[ReferralReferenceKey] = Field(default_factory=list)
    programCode: str = Field(..., min_length=1, max_length=64)             # validated
    referralCode: str = Field(..., min_length=1, max_length=64)            # validated

    @validator("prospectAccountKeyType")
    def _v_account_key_type(cls, v: str) -> str:
        # Extend as needed; acceptance wants CARD_ACCOUNT_ID today
        if v not in {"CARD_ACCOUNT_ID"}:
            raise BadRequest(40004, "Invalid account key type")
        return v

    @validator("referralCode")
    def _v_referral_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v):
            raise BadRequest(40003, "Invalid referral code format")
        return v

    @validator("programCode")
    def _v_program_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v):
            raise BadRequest(40005, "Invalid referral program code")
        return v

class ReferralCreateResponse(BaseModel):
    referralId: str

class ErrorBody(BaseModel):
    id: int
    developerText: str



##############################


"""
Pulls DB connection settings straight from environment variables.
No URL/JDBC parsing. We expect these EXACT names to be set by CloudFormation:

- DB_NAME
- DB_USERNAME
- DB_PASSWORD
- DB_HOST
- DB_PORT   (string, e.g., "5432")

Returns a tuple suitable for db_util.connection.create_connection(...).
"""

from __future__ import annotations
import os

_REQUIRED = ("DB_NAME", "DB_USERNAME", "DB_PASSWORD", "DB_HOST", "DB_PORT")

def get_db_params() -> tuple[str, str, str, str, str]:
    """
    Returns (db_name, db_user, db_password, db_host, db_port).

    Raises:
        KeyError: when one or more required env vars are missing/empty
        ValueError: when DB_PORT is not a positive integer string
    """
    # Grab and trim env vars so accidental spaces don't slip through
    env = {k: (os.getenv(k) or "").strip() for k in _REQUIRED}
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise KeyError(f"Missing required environment variable(s): {', '.join(missing)}")

    # Light sanity check on port; keep as string for create_connection signature parity
    if not env["DB_PORT"].isdigit() or int(env["DB_PORT"]) <= 0:
        raise ValueError("DB_PORT must be a positive integer string, e.g., '5432'")

    return env["DB_NAME"], env["DB_USERNAME"], env["DB_PASSWORD"], env["DB_HOST"], env["DB_PORT"]




##########


"""
DB insert for `fulfillment_event` using your helper: db_util.connection.create_connection()

Design goals:
- NO URL parsing; we strictly read 5 env vars via utils.database_utils.get_db_params()
- Small inline retry loop (default 5) with tiny backoff, friendly logs
- JSONB write for referralReferenceKeys
- Always closes cursor/connection
"""

from __future__ import annotations
import json
import logging
import time
from typing import Any, Dict

from db_util.connection import create_connection  # provided by your org
from ..utils.database_utils import get_db_params

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Parameterized SQL with RETURNING so we can confirm success and send a Location link
_SQL = """
INSERT INTO fulfillment_event
  (prospect_account_key,
   prospect_account_key_type,
   sor_id,
   program_code,
   referral_code,
   referral_reference_keys)
VALUES (%s, %s, %s, %s, %s, %s::jsonb)
RETURNING referral_id;
""".strip()

def create_referral_fulfillment(payload: Dict[str, Any], retries: int = 5) -> str:
    """
    Inserts one row and returns the generated `referral_id` as a string.

    Args:
        payload: already validated by Pydantic upstream.
        retries: total attempts on transient failures (e.g., network hiccups).

    Raises:
        Exception: the last raised error if all attempts fail.
        RuntimeError: if the DB executes but returns no referral_id.
    """
    # 1) Gather connection parms from env (strict)
    db_name, db_user, db_password, db_host, db_port = get_db_params()

    # 2) Prepare bind parameters in a fixed, predictable order
    params = [
        payload["prospectAccountKey"],
        payload["prospectAccountKeyType"],
        payload["sorId"],
        payload["programCode"],
        payload["referralCode"],
        json.dumps(payload.get("referralReferenceKeys", [])),
    ]

    last_err: Exception | None = None

    # 3) Friendly, understandable retry loop with small linear backoff
    for attempt in range(1, retries + 1):
        conn = None
        cur = None
        try:
            logger.info("db-connect attempt=%s host=%s db=%s user=%s", attempt, db_host, db_name, db_user)
            conn = create_connection(
                db_name=db_name,
                db_user=db_user,
                db_password=db_password,
                db_host=db_host,
                db_port=db_port,
            )
            # `with conn:` lets psycopg2 auto-handle commit/rollback for us
            with conn:
                cur = conn.cursor()
                cur.execute(_SQL, params)
                row = cur.fetchone()
                if not row or not row[0]:
                    # The INSERT ran but didn't produce an id; treat as failure
                    raise RuntimeError("DB returned no referral_id")
                rid = str(row[0])
                logger.info("db-insert success attempt=%s referral_id=%s", attempt, rid)
                return rid
        except Exception as e:
            # Transient or persistent error — record it and decide about retrying
            last_err = e
            logger.warning("db-insert failure attempt=%s err=%r", attempt, e)
            if attempt < retries:
                # Tiny backoff: easy to read, capped at 1s
                time.sleep(min(0.2 * attempt, 1.0))
        finally:
            # 4) Always release resources (best effort)
            try:
                if cur is not None:
                    cur.close()
            except Exception as e:
                logger.debug("cursor.close ignored: %r", e)
            try:
                if conn is not None:
                    conn.close()
            except Exception as e:
                logger.debug("conn.close ignored: %r", e)

    # 5) If we reach here, all attempts failed
    assert last_err is not None
    logger.error("db-insert exhausted retries=%s last_err=%r", retries, last_err)
    raise last_err


#############


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

@app.post("/enterprise/referrals")
def create_referral() -> Dict[str, Any]:
    # Parse JSON body (Powertools exposes current_event.json_body)
    try:
        body = app.current_event.json_body or {}
    except Exception:
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=40001, developerText="Missing required field in request (body)").model_dump())

    # Validate + map 400xx
    try:
        req = ReferralCreateRequest.model_validate(body)
    except Exception as e:
        code, message = map_validation_to_400xx(e)
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=code, developerText=message).model_dump())

    # Write to DB
    try:
        rid = create_referral_fulfillment(req.model_dump())
    except Exception:
        logger.exception("db failure")
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorBody(id=50000, developerText="Internal Server Error").model_dump())

    # 201 + Location
    host = app.current_event.headers.get("host", "")
    proto = app.current_event.headers.get("x-forwarded-proto", "https")
    location = f"{proto}://{host}/enterprise/referrals/{rid}" if host else f"/enterprise/referrals/{rid}"
    return _resp(HTTPStatus.CREATED, ReferralCreateResponse(referralId=rid).model_dump(), headers={"Location": location})

@app.not_found
def not_found(event) -> Dict[str, Any]:
    return _resp(HTTPStatus.NOT_FOUND, {"error": "Endpoint does not exist"})

@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: Dict[str, Any], context: LambdaContext):
    return app.resolve(event, context)




##########################


import os
import unittest
from unittest.mock import patch
from src.utils.database_utils import get_db_params

class TestUtils(unittest.TestCase):
    @patch.dict(os.environ, {
        "DB_NAME": "refl_db",
        "DB_USERNAME": "enrollment_usr",
        "DB_PASSWORD": "secret",
        "DB_HOST": "db.example.com",
        "DB_PORT": "5432",
    }, clear=True)
    def test_ok(self):
        self.assertEqual(
            get_db_params(),
            ("refl_db", "enrollment_usr", "secret", "db.example.com", "5432")
        )

    @patch.dict(os.environ, {
        "DB_NAME": "refl_db",
        "DB_USERNAME": "user",
        "DB_PASSWORD": "pw",
        "DB_HOST": "db.example.com",
        "DB_PORT": "notanumber",
    }, clear=True)
    def test_bad_port(self):
        with self.assertRaises(ValueError):
            get_db_params()

    @patch.dict(os.environ, {
        "DB_NAME": "refl_db",
        "DB_USERNAME": "user",
        "DB_PASSWORD": "pw",
        "DB_HOST": "db.example.com",
        # DB_PORT missing
    }, clear=True)
    def test_missing(self):
        with self.assertRaises(KeyError):
            get_db_params()

    @patch.dict(os.environ, {
        "DB_NAME": " ",
        "DB_USERNAME": "user",
        "DB_PASSWORD": "pw",
        "DB_HOST": "db.example.com",
        "DB_PORT": "5432",
    }, clear=True)
    def test_blank_values(self):
        with self.assertRaises(KeyError):
            get_db_params()




#######################



import os
import unittest
from unittest.mock import MagicMock, patch
from src.database.db import create_referral_fulfillment

BASE = {
    "prospectAccountKey": "123",
    "prospectAccountKeyType": "CARD_ACCOUNT_ID",
    "sorId": "SOR1",
    "programCode": "PROGRAM_001",
    "referralCode": "REFERRAL_ABC",
    "referralReferenceKeys": [{"referralReferenceKeyName":"K","referralReferenceKeyValue":"V"}],
}

def make_conn():
    conn = MagicMock(name="conn")
    cur = MagicMock(name="cursor")
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    conn.cursor.return_value = cur
    return conn, cur

BASE_ENV = {
    "DB_NAME": "refl_db",
    "DB_USERNAME": "user",
    "DB_PASSWORD": "pw",
    "DB_HOST": "db.example.com",
    "DB_PORT": "5432",
}

@patch.dict(os.environ, BASE_ENV, clear=True)
class TestDB(unittest.TestCase):
    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    def test_success(self, _sleep, create_conn_mock):
        conn, cur = make_conn()
        cur.fetchone.return_value = ["RID-1"]
        create_conn_mock.return_value = conn

        rid = create_referral_fulfillment(BASE)
        self.assertEqual(rid, "RID-1")
        cur.execute.assert_called_once()
        cur.close.assert_called_once()
        conn.close.assert_called_once()

    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    def test_transient_then_ok(self, _sleep, create_conn_mock):
        conn, cur = make_conn()
        create_conn_mock.return_value = conn

        def side_effect(*_a, **_k):
            if side_effect.calls < 1:
                side_effect.calls += 1
                raise RuntimeError("blip")
            cur.fetchone.return_value = ["RID-2"]
        side_effect.calls = 0
        cur.execute.side_effect = side_effect

        rid = create_referral_fulfillment(BASE, retries=3)
        self.assertEqual(rid, "RID-2")
        self.assertGreaterEqual(conn.close.call_count, 1)

    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    def test_no_referral_id(self, _sleep, create_conn_mock):
        conn, cur = make_conn()
        create_conn_mock.return_value = conn
        cur.fetchone.return_value = None
        with self.assertRaises(RuntimeError):
            create_referral_fulfillment(BASE)

    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    def test_exhausted(self, _sleep, create_conn_mock):
        conn, cur = make_conn()
        create_conn_mock.return_value = conn
        cur.execute.side_effect = RuntimeError("down")
        with self.assertRaises(RuntimeError):
            create_referral_fulfillment(BASE, retries=2)

@patch.dict(os.environ, {**BASE_ENV, "DB_PORT":"bogus"}, clear=True)
class TestDBEnvError(unittest.TestCase):
    # Ensures get_db_params() failure bubbles up cleanly
    @patch("src.database.db.create_connection")
    def test_env_validation_bubbles(self, _):
        with self.assertRaises(ValueError):
            create_referral_fulfillment(BASE)




##########################


import json
import unittest
from unittest.mock import patch
from src.main import app, create_referral

class FakeEvent:
    def __init__(self, body: dict | None, headers=None):
        self.headers = headers or {"host":"api.example.com","x-forwarded-proto":"https"}
        self._body = body
    @property
    def json_body(self):
        if self._body is None:
            raise ValueError("bad json")
        return self._body

class TestHandler(unittest.TestCase):
    def set_event(self, body):
        app._current_event = FakeEvent(body)  # type: ignore

    @patch("src.main.create_referral_fulfillment", return_value="123")
    def test_201(self, _db):
        body = {
            "prospectAccountKey":"123",
            "prospectAccountKeyType":"CARD_ACCOUNT_ID",
            "sorId":"S",
            "referralReferenceKeys":[],
            "programCode":"PROGRAM_001",
            "referralCode":"REFERRAL_ABC",
        }
        self.set_event(body)
        res = create_referral()
        self.assertEqual(res["statusCode"], 201)
        payload = json.loads(res["body"])
        self.assertEqual(payload["referralId"], "123")
        self.assertIn("/enterprise/referrals/123", res["headers"]["Location"])

    def test_400_missing_body(self):
        app._current_event = FakeEvent(None)  # type: ignore
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)

    def test_400_validation(self):
        self.set_event({"programCode":"BAD SPACE"})  # intentionally invalid/missing
        res = create_referral()
        self.assertEqual(res["statusCode"], 400)

    @patch("src.main.create_referral_fulfillment", side_effect=RuntimeError("db down"))
    def test_500_db(self, _db):
        body = {
            "prospectAccountKey":"123",
            "prospectAccountKeyType":"CARD_ACCOUNT_ID",
            "sorId":"S",
            "referralReferenceKeys":[],
            "programCode":"PROGRAM_001",
            "referralCode":"REFERRAL_ABC",
        }
        self.set_event(body)
        res = create_referral()
        self.assertEqual(res["statusCode"], 500)






###############################




import unittest
from pydantic import ValidationError
from src.models.model_referral import ReferralCreateRequest, map_validation_to_400xx

class TestModels(unittest.TestCase):
    def base(self):
        return dict(
            prospectAccountKey="123",
            prospectAccountKeyType="CARD_ACCOUNT_ID",
            sorId="SOR1",
            referralReferenceKeys=[{"referralReferenceKeyName":"K","referralReferenceKeyValue":"V"}],
            programCode="PROGRAM_001",
            referralCode="REFERRAL_ABC",
        )

    def test_ok(self):
        req = ReferralCreateRequest(**self.base())
        self.assertEqual(req.referralCode, "REFERRAL_ABC")

    def test_missing_field_40001(self):
        b = self.base(); b.pop("prospectAccountKey")
        with self.assertRaises(ValidationError) as ctx:
            ReferralCreateRequest(**b)
        code, _ = map_validation_to_400xx(ctx.exception)
        self.assertEqual(code, 40001)

    def test_invalid_account_type_40004(self):
        b = self.base(); b["prospectAccountKeyType"] = "WRONG"
        with self.assertRaises(Exception) as ctx:
            ReferralCreateRequest(**b)
        code, _ = map_validation_to_400xx(ctx.exception)
        self.assertEqual(code, 40004)

    def test_invalid_referral_code_40003(self):
        b = self.base(); b["referralCode"] = "bad space"
        with self.assertRaises(Exception) as ctx:
            ReferralCreateRequest(**b)
        code, _ = map_validation_to_400xx(ctx.exception)
        self.assertEqual(code, 40003)

    def test_invalid_program_code_40005(self):
        b = self.base(); b["programCode"] = "bad space"
        with self.assertRaises(Exception) as ctx:
            ReferralCreateRequest(**b)
        code, _ = map_validation_to_400xx(ctx.exception)
        self.assertEqual(code, 40005)





