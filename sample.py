from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Tuple

from db_util.connection import create_connection  # provided by your pyref/db-util
from src.utils.database_utils import fetch_db_params_from_secret

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_SQL = """
INSERT INTO fulfillment_event
(
  prospect_account_key,
  prospect_account_key_type,
  sor_id,
  program_code,
  referral_code,
  referral_reference_keys
)
VALUES (%s, %s, %s, %s, %s, %s::jsonb)
RETURNING referral_id;
""".strip()


def _get_db_params() -> Tuple[str, str, str, str, int]:
    """Prefer explicit env vars; otherwise fall back to Secrets Manager."""
    need = ("DB_NAME", "DB_USERNAME", "DB_PASSWORD", "DB_HOST", "DB_PORT")
    env = os.environ
    if all(k in env for k in need):
        try:
            port = int(env["DB_PORT"])
        except Exception as exc:
            raise ValueError("DB_PORT must be an integer") from exc
        return env["DB_NAME"], env["DB_USERNAME"], env["DB_PASSWORD"], env["DB_HOST"], port

    name, user, pwd, host, port = fetch_db_params_from_secret()
    return name, user, pwd, host, int(port)


def create_referral_fulfillment(payload: Dict[str, Any], retries: int = 3) -> str:
    """
    Insert a fulfillment row and return referral_id as string.
    The payload is already validated by the API layer.
    """
    db_name, db_user, db_password, db_host, db_port = _get_db_params()
    params = [
        payload["prospectAccountKey"],
        payload["prospectAccountKeyType"],
        payload["sorId"],
        payload["programCode"],
        payload["referralCode"],
        json.dumps(payload.get("referralReferenceKeys", [])),
    ]

    last_err: Exception | None = None

    for attempt in range(1, retries + 1):
        conn = None
        cur = None
        try:
            conn = create_connection(
                db_name=db_name,
                db_user=db_user,
                db_password=db_password,
                db_host=db_host,
                db_port=db_port,
            )
            with conn:  # relies on DB driver autocommit/commit/rollback behavior
                cur = conn.cursor()
                cur.execute(_SQL, params)
                row = cur.fetchone()
                if not row or not row[0]:
                    raise RuntimeError("DB returned no referral_id")
                rid = str(row[0])
                logger.info("db-insert success attempt=%s referral_id=%s", attempt, rid)
                return rid
        except Exception as e:  # pragma: no cover - line executed, branch covered below
            last_err = e
            logger.warning("db-insert failure attempt=%s err=%r", attempt, e)
            if attempt < retries:
                time.sleep(min(0.2 * attempt, 1.0))
        finally:
            try:
                if cur is not None:
                    cur.close()
            except Exception as e:  # pragma: no cover - defensive logging
                logger.debug("cursor.close ignored: %r", e)
            try:
                if conn is not None:
                    conn.close()
            except Exception as e:  # pragma: no cover - defensive logging
                logger.debug("conn.close ignored: %r", e)

    assert last_err is not None
    logger.error("db-insert exhausted retries=%s last_error=%r", retries, last_err)
    raise last_err



##########################

from __future__ import annotations

import ast
import json
import os
from typing import Tuple

import boto3
from aws_util import retrieve_secret_value  # your helper that wraps SM get_secret_value


def fetch_db_params_from_secret() -> Tuple[str, str, str, str, int]:
    """
    Pull DB credentials from AWS Secrets Manager.
    Supports secrets stored as JSON; falls back to python-literal strings.
    """
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        raise ValueError("AWS region is not set (AWS_REGION / AWS_DEFAULT_REGION)")

    secret_name = os.environ["DB_SECRET_ARN"]
    sm = boto3.client("secretsmanager", region_name=region)
    raw = retrieve_secret_value(sm, secret_name)

    # Try JSON first, then literal_eval as a safe fallback for legacy formats.
    secret: dict | None = None
    if raw:
        try:
            secret = json.loads(raw)
        except Exception:
            try:
                secret = ast.literal_eval(raw)
            except Exception:
                secret = None

    if not secret:
        raise ValueError(f"Failed to retrieve secret for {secret_name}")

    required = ("dbname", "username", "password", "host", "port")
    if any(k not in secret for k in required):
        raise ValueError("Secret is missing one or more required keys")

    return (
        str(secret["dbname"]),
        str(secret["username"]),
        str(secret["password"]),
        str(secret["host"]),
        int(secret["port"]),
    )



##################################



from __future__ import annotations

import re
from typing import List, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator


class BadRequest(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)


def map_validation_to_400xx(exc: Exception) -> Tuple[int, str]:
    if isinstance(exc, BadRequest):
        return exc.code, str(exc)

    if isinstance(exc, ValidationError):
        errors = exc.errors()

        # Missing fields
        for err in errors:
            etype = (err.get("type") or "").lower()
            if etype == "missing" or etype.endswith("missing"):
                loc = ".".join(str(p) for p in err.get("loc", [])) or "field"
                return 40001, f"Missing required field in request ({loc})"

        # Specific messages surfaced by our validators
        for err in errors:
            msg = (err.get("msg") or "").strip()
            if "Invalid account key type" in msg:
                return 40004, "Invalid account key type"
            if "Invalid referral code format" in msg:
                return 40003, "Invalid referral code format"
            if "Invalid referral program code" in msg:
                return 40005, "Invalid referral program code"

        # Generic invalid field
        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", [])) or "field"
            return 40002, f"Invalid value for field ({loc})"

    return 40002, "Invalid value"


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
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v or ""):
            raise BadRequest(40003, "Invalid referral code format")
        return v

    @field_validator("programCode")
    @classmethod
    def _v_program_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v or ""):
            raise BadRequest(40005, "Invalid referral program code")
        return v


class ReferralCreateResponse(BaseModel):
    referralId: str


class ErrorBody(BaseModel):
    id: int
    developerText: str





##############################


from __future__ import annotations

import json
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Dict

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import ALBResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.database.db import create_referral_fulfillment
from src.models.model_referral import (
    ErrorBody,
    ReferralCreateRequest,
    ReferralCreateResponse,
    map_validation_to_400xx,
)

logger = Logger()
app = ALBResolver()


@app.get("/referrals/health")
def health_check():
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "healthy", "message": "Service is running smoothly"}),
    }


@app.patch("/enterprise/referrals/{referral_id}")
def update_referral(referral_id: str):
    logger.info(f"Updating referral with ID: {referral_id}")
    _ = app.current_event.json_body  # recorded for logs
    return {"statusCode": 204, "body": ""}


@app.not_found
def handle_not_found(event):
    logger.warning("Resource not found")
    logger.warning(event)
    return {"statusCode": 404, "body": json.dumps({"error": "Endpoint does not exist"})}


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: dict, context: LambdaContext):
    return app.resolve(event, context)


def _resp(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


@app.post("/enterprise/referrals")
def create_referral() -> Dict[str, Any]:
    # 1) Parse body
    try:
        body = app.current_event.json_body or {}
    except Exception:
        return _resp(
            HTTPStatus.BAD_REQUEST,
            ErrorBody(id=40001, developerText="Missing required field in request (body)").model_dump(),
        )

    # 2) Validate
    try:
        req = ReferralCreateRequest.model_validate(body)
    except Exception as e:
        code, message = map_validation_to_400xx(e)
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=code, developerText=message).model_dump())

    # 3) DB insert
    try:
        rid = create_referral_fulfillment(req.model_dump())
    except Exception:
        logger.exception("db failure")
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorBody(id=50000, developerText="Internal Server Error").model_dump())

    # 4) Log minimal creation info
    created_at = datetime.now(timezone.utc).isoformat()
    path = f"/enterprise/referrals/{rid}"
    logger.info(f"referral created referralId={rid} createdAt={created_at} path={path}")

    # 5) Return referralId only, as per spec
    return _resp(HTTPStatus.CREATED, ReferralCreateResponse(referralId=rid).model_dump())




##########################



import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.database import db as db_mod


def _valid_payload():
    return {
        "prospectAccountKey": "123456789",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "SOR123",
        "programCode": "PROGRAM_001",
        "referralCode": "REF_ABC",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X", "referralReferenceKeyValue": "Y"}],
    }


def test__get_db_params_from_env(monkeypatch):
    env = {
        "DB_NAME": "n",
        "DB_USERNAME": "u",
        "DB_PASSWORD": "p",
        "DB_HOST": "h",
        "DB_PORT": "5432",
    }
    monkeypatch.setenv("DB_NAME", env["DB_NAME"])
    monkeypatch.setenv("DB_USERNAME", env["DB_USERNAME"])
    monkeypatch.setenv("DB_PASSWORD", env["DB_PASSWORD"])
    monkeypatch.setenv("DB_HOST", env["DB_HOST"])
    monkeypatch.setenv("DB_PORT", env["DB_PORT"])

    assert db_mod._get_db_params() == ("n", "u", "p", "h", 5432)


def test__get_db_params_from_secret(monkeypatch):
    # unset env path so secret path is taken
    for k in ("DB_NAME", "DB_USERNAME", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
        monkeypatch.delenv(k, raising=False)

    with patch("src.database.db.fetch_db_params_from_secret") as f:
        f.return_value = ("sn", "su", "sp", "sh", 15432)
        assert db_mod._get_db_params() == ("sn", "su", "sp", "sh", 15432)


def test_create_referral_fulfillment_success(monkeypatch):
    # ensure env path is used to avoid secrets
    monkeypatch.setenv("DB_NAME", "n")
    monkeypatch.setenv("DB_USERNAME", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_PORT", "5432")

    # fake DB connection / cursor
    class Cursor:
        def __init__(self):
            self.executed = None

        def execute(self, sql, params):
            self.executed = (sql, params)

        def fetchone(self):
            return (987654321,)

        def close(self):  # pragma: no cover - exercised by finally
            pass

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return Cursor()

        def close(self):  # pragma: no cover
            pass

    monkeypatch.setattr(db_mod, "create_connection", lambda **_: Conn())

    rid = db_mod.create_referral_fulfillment(_valid_payload())
    assert rid == "987654321"


def test_create_referral_fulfillment_retries_then_raises(monkeypatch):
    monkeypatch.setenv("DB_NAME", "n")
    monkeypatch.setenv("DB_USERNAME", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_PORT", "5432")

    calls = {"n": 0}

    class Cursor:
        def execute(self, *_a, **_kw):
            calls["n"] += 1
            raise RuntimeError("boom")

        def fetchone(self):
            return None

        def close(self):  # pragma: no cover
            pass

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return Cursor()

        def close(self):  # pragma: no cover
            pass

    monkeypatch.setattr(db_mod, "create_connection", lambda **_: Conn())

    with pytest.raises(RuntimeError):
        db_mod.create_referral_fulfillment(_valid_payload(), retries=2)

    # at least two attempts
    assert calls["n"] >= 2



#######################


import os
from unittest.mock import MagicMock, patch

import pytest

from src.utils.database_utils import fetch_db_params_from_secret


@patch("src.utils.database_utils.boto3.client")
@patch("src.utils.database_utils.retrieve_secret_value")
def test_fetch_params_ok(mock_retrieve, mock_client, monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:abc")

    mock_client.return_value = MagicMock()
    mock_retrieve.return_value = (
        '{"dbname":"d","username":"u","password":"p","host":"h","port":5432}'
    )

    got = fetch_db_params_from_secret()
    assert got == ("d", "u", "p", "h", 5432)


@patch("src.utils.database_utils.boto3.client")
@patch("src.utils.database_utils.retrieve_secret_value")
def test_fetch_params_bad_payload_raises(mock_retrieve, mock_client, monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("DB_SECRET_ARN", "arn")
    mock_client.return_value = MagicMock()
    mock_retrieve.return_value = "not a json or literal"
    with pytest.raises(ValueError):
        fetch_db_params_from_secret()




###########################


import json
from http import HTTPStatus
from unittest.mock import patch

from src.main import lambda_handler


def _alb_event(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    return {
        "httpMethod": method,
        "path": path,
        "isBase64Encoded": False,
        "headers": {
            "content-type": "application/json",
            "x-forwarded-proto": "https",
            "host": "example.com",
            **(headers or {}),
        },
        "queryStringParameters": None,
        "requestContext": {"elb": {"targetGroupArn": "arn:aws:elasticloadbalancing:..."}},
        "body": None if body is None else json.dumps(body),
    }


def test_health():
    ev = _alb_event("GET", "/referrals/health")
    res = lambda_handler(ev, {})  # context not used
    assert res["statusCode"] == 200
    payload = json.loads(res["body"])
    assert payload["status"] == "healthy"


@patch("src.main.create_referral_fulfillment", return_value="123")
def test_create_referral_201(_mock_db):
    body = {
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
        "referralReferenceKeys": [],
    }
    ev = _alb_event("POST", "/enterprise/referrals", body=body)
    res = lambda_handler(ev, {})
    assert res["statusCode"] == HTTPStatus.CREATED
    assert json.loads(res["body"]) == {"referralId": "123"}


def test_create_referral_400_missing_body():
    ev = _alb_event("POST", "/enterprise/referrals", body=None, headers={"content-type": "text/plain"})
    # ALB resolver will try to parse; with non-JSON, we still get missing body path (caught in main)
    res = lambda_handler(ev, {})
    assert res["statusCode"] == HTTPStatus.BAD_REQUEST
    body = json.loads(res["body"])
    assert body["id"] == 40001


def test_create_referral_400_validation_error():
    # missing required programCode -> id 40001
    bad = {
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "referralCode": "REF_001",
    }
    ev = _alb_event("POST", "/enterprise/referrals", body=bad)
    res = lambda_handler(ev, {})
    assert res["statusCode"] == HTTPStatus.BAD_REQUEST
    assert json.loads(res["body"])["id"] == 40001


@patch("src.main.create_referral_fulfillment", side_effect=RuntimeError("db down"))
def test_create_referral_500(_mock_db):
    good = {
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
    }
    ev = _alb_event("POST", "/enterprise/referrals", body=good)
    res = lambda_handler(ev, {})
    assert res["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert json.loads(res["body"])["id"] == 50000


def test_update_referral_204():
    ev = _alb_event("PATCH", "/enterprise/referrals/abc", body={"x": 1})
    res = lambda_handler(ev, {})
    assert res["statusCode"] == 204


def test_not_found_404():
    ev = _alb_event("GET", "/nope")
    res = lambda_handler(ev, {})
    assert res["statusCode"] == 404

