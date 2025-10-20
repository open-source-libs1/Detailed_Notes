



from __future__ import annotations
import os
from urllib.parse import urlparse

def get_db_params() -> tuple[str, str, str, str, str]:
    """
    Return (db_name, db_user, db_password, db_host, db_port) from env.

    Required:
      - DB_URL: supports:
          * postgresql://user:pass@host:5432/db
          * postgres://user:pass@host:5432/db
          * jdbc:postgresql://host:5432/db    (no creds in URL; use overrides)
    Optional overrides:
      - DB_USERNAME
      - DB_PASSWORD
    """
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise KeyError("Missing required environment variable: DB_URL")

    # normalize jdbc prefix
    if db_url.startswith("jdbc:"):
        db_url = db_url[len("jdbc:"):]

    p = urlparse(db_url)
    if not (p.scheme and p.scheme.startswith("postgres")):
        raise ValueError("DB_URL must start with postgres://, postgresql://, or jdbc:postgresql://")

    name = (p.path or "").lstrip("/") or None
    u, pw, host, port = p.username, p.password, p.hostname, p.port

    db_user = os.getenv("DB_USERNAME") or u or ""
    db_password = os.getenv("DB_PASSWORD") or pw or ""
    db_name = name or ""
    db_host = host or ""
    db_port = str(port or "5432")

    missing = [k for k, v in {
        "db_name": db_name, "db_user": db_user, "db_password": db_password,
        "db_host": db_host, "db_port": db_port
    }.items() if not v]
    if missing:
        raise RuntimeError(f"DB configuration incomplete; missing: {', '.join(missing)}")

    return db_name, db_user, db_password, db_host, db_port


############################


from __future__ import annotations
import json
import logging
import os
import time
from typing import Any, Dict

import psycopg            # psycopg3
from psycopg_pool import AsyncConnectionPool

from ..utils.database_utils import get_db_params

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level async pool (cold-start friendly for Lambda)
_POOL: AsyncConnectionPool | None = None

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

def _conninfo() -> str:
    db_name, db_user, db_password, db_host, db_port = get_db_params()
    return (
        f"dbname={db_name} user={db_user} password={db_password} "
        f"host={db_host} port={db_port} connect_timeout=5"
    )

def _pool(min_connections: int | None = None, max_connections: int | None = None) -> AsyncConnectionPool:
    """
    Get or create a global AsyncConnectionPool with configured min/max size.
    You can pass explicit sizes, or rely on env:
      - DB_POOL_MIN (default 1)
      - DB_POOL_MAX (default 5)
    """
    global _POOL
    if _POOL is None:
        min_size = int(min_connections or os.getenv("DB_POOL_MIN", "1"))
        max_size = int(max_connections or os.getenv("DB_POOL_MAX", "5"))
        # Safety: min <= max and >= 1
        min_size = max(1, min_size)
        max_size = max(min_size, max_size)

        _POOL = AsyncConnectionPool(
            conninfo=_conninfo(),
            min_size=min_size,
            max_size=max_size,
            kwargs={
                "options": "-c statement_timeout=10000 -c idle_in_transaction_session_timeout=10000",
                "application_name": os.getenv("APP_NAME", "referrals-lambda"),
            },
        )
        logger.info("db-pool initialized min=%s max=%s", min_size, max_size)
    return _POOL

def create_connection(*, min_connections: int | None = None, max_connections: int | None = None):
    """
    Return an **async context manager** for a pooled connection.

    Usage:
      async with create_connection() as conn:
          ...

    Pool sizes can be provided here, or via env (DB_POOL_MIN/DB_POOL_MAX).
    """
    return _pool(min_connections, max_connections).connection()  # async context manager

async def create_referral_fulfillment(payload: Dict[str, Any], retries: int = 5) -> str:
    """
    Async insert returning its referral_id.

    Backoff: 0.2s * attempt (capped at 1s). Connections/cursors are closed by context managers.
    Raises the last exception if all attempts fail or DB returns no id.
    """
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
        try:
            async with create_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(_SQL, params)
                    row = await cur.fetchone()
                    if not row or not row[0]:
                        raise RuntimeError("DB returned no referral_id")
                    rid = str(row[0])
                    logger.info("db-insert success attempt=%s referral_id=%s", attempt, rid)
                    return rid
        except Exception as e:
            last_err = e
            logger.warning("db-insert failure attempt=%s err=%r", attempt, e)
            if attempt < retries:
                time.sleep(min(0.2 * attempt, 1.0))

    assert last_err is not None
    logger.error("db-insert exhausted retries=%s last_err=%r", retries, last_err)
    raise last_err



################################


from __future__ import annotations
import re
from typing import List
from pydantic import BaseModel, Field, ValidationError, field_validator

# ---- Errors + mapping --------------------------------------------------------

class BadRequest(ValueError):
    """Encode specific 400xx codes from business validation."""
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)

def map_validation_to_400xx(exc: Exception) -> tuple[int, str]:
    """
    Priority:
      1) BadRequest -> explicit 400xx
      2) Pydantic missing field -> 40001
      3) Otherwise -> 40002 (invalid value)
    """
    if isinstance(exc, BadRequest):
        return exc.code, str(exc)

    if isinstance(exc, ValidationError):
        errors = exc.errors()
        for err in errors:
            etype = (err.get("type") or "").lower()  # v2: "missing"
            if etype == "missing":
                loc = ".".join(str(p) for p in err.get("loc", [])) or "field"
                return (40001, f"Missing required field in request ({loc})")
        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", [])) or "field"
            return (40002, f"Invalid value for field {loc}")
        return (40002, "Invalid value")

    return (40002, "Invalid value")

# ---- Models ------------------------------------------------------------------

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
            # 40004 Invalid account key type
            raise BadRequest(40004, "Invalid account key type")
        return v

    @field_validator("referralCode")
    @classmethod
    def _v_referral_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v):
            # 40003 Invalid referral code format
            raise BadRequest(40003, "Invalid referral code format")
        return v

    @field_validator("programCode")
    @classmethod
    def _v_program_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v):
            # 40005 Invalid referral program code
            raise BadRequest(40005, "Invalid referral program code")
        return v

class ReferralCreateResponse(BaseModel):
    referralId: str

class ErrorBody(BaseModel):
    id: int
    developerText: str



#################################


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
async def create_referral() -> Dict[str, Any]:
    try:
        body = app.current_event.json_body or {}
    except Exception:
        return _resp(
            HTTPStatus.BAD_REQUEST,
            ErrorBody(id=40001, developerText="Missing required field in request (body)").model_dump()
        )

    try:
        req = ReferralCreateRequest(**body)
    except Exception as e:
        code, message = map_validation_to_400xx(e)
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=code, developerText=message).model_dump())

    try:
        rid = await create_referral_fulfillment(req.model_dump())
    except Exception:
        logger.exception("db failure")
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorBody(id=50000, developerText="Internal Server Error").model_dump())

    host = app.current_event.headers.get("host", "")
    proto = app.current_event.headers.get("x-forwarded-proto", "https")
    location = f"{proto}://{host}/enterprise/referrals/{rid}" if host else f"/enterprise/referrals/{rid}"
    return _resp(HTTPStatus.CREATED, ReferralCreateResponse(referralId=rid).model_dump(), headers={"Location": location})

@app.not_found
def not_found(event) -> Dict[str, Any]:
    return _resp(HTTPStatus.NOT_FOUND, {"error": "Endpoint does not exist"})

@logger.inject_lambda_context(log_event=True)
async def lambda_handler(event: Dict[str, Any], context: LambdaContext):
    return await app.resolve(event, context)




#############################


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




#############################


import os
import unittest
from unittest.mock import patch
from src.utils.database_utils import get_db_params

class TestUtils(unittest.TestCase):
    @patch.dict(os.environ, {"DB_URL":"postgresql://u:p@h:5432/n"}, clear=True)
    def test_params_from_pg_url(self):
        self.assertEqual(get_db_params(), ("n","u","p","h","5432"))

    @patch.dict(os.environ, {"DB_URL":"jdbc:postgresql://h:5432/n","DB_USERNAME":"X","DB_PASSWORD":"Y"}, clear=True)
    def test_params_from_jdbc_with_overrides(self):
        self.assertEqual(get_db_params(), ("n","X","Y","h","5432"))

    @patch.dict(os.environ, {"DB_URL":"jdbc:postgresql://h:5432/n"}, clear=True)
    def test_missing_creds_raises(self):
        with self.assertRaises(RuntimeError):
            get_db_params()

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_url_raises(self):
        with self.assertRaises(KeyError):
            get_db_params()




###################################


import os
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from src.database.db import create_referral_fulfillment

BASE = {
    "prospectAccountKey": "123",
    "prospectAccountKeyType": "CARD_ACCOUNT_ID",
    "sorId": "SOR1",
    "programCode": "PROGRAM_001",
    "referralCode": "REFERRAL_ABC",
    "referralReferenceKeys": [{"referralReferenceKeyName":"K","referralReferenceKeyValue":"V"}],
}

class _AsyncConnCtx:
    """Async context manager that yields a conn with async cursor()."""
    def __init__(self, cur_fetch):
        self.conn = MagicMock(name="conn")
        self._cur = MagicMock(name="cursor")
        # Async cursor() returning async context manager
        async def _aenter():
            return self._cur
        async def _aexit(_exc_type, _exc, _tb):
            return False
        self.conn.cursor = MagicMock(return_value=type("CurCtx", (), {
            "__aenter__": staticmethod(_aenter),
            "__aexit__": staticmethod(_aexit),
        })())
        # async methods on cursor
        self._cur.execute = AsyncMock()
        self._cur.fetchone = AsyncMock(side_effect=cur_fetch)

    async def __aenter__(self):
        return self.conn
    async def __aexit__(self, exc_type, exc, tb):
        return False

@patch.dict(os.environ, {"DB_URL":"postgresql://u:p@h:5432/n"}, clear=True)
class TestDB(unittest.IsolatedAsyncioTestCase):
    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    async def test_success(self, _sleep, create_conn_mock):
        ctx = _AsyncConnCtx(cur_fetch=lambda: ["RID-1"])
        create_conn_mock.return_value = ctx
        rid = await create_referral_fulfillment(BASE)
        self.assertEqual(rid, "RID-1")
        create_conn_mock.assert_called()

    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    async def test_transient_then_ok(self, _sleep, create_conn_mock):
        calls = {"n": 0}
        async def fetch():
            if calls["n"] == 0:
                calls["n"] += 1
                return None  # force "no id", triggers retry
            return ["RID-2"]
        ctx = _AsyncConnCtx(cur_fetch=fetch)
        create_conn_mock.return_value = ctx
        rid = await create_referral_fulfillment(BASE, retries=3)
        self.assertEqual(rid, "RID-2")

    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    async def test_no_referral_id(self, _sleep, create_conn_mock):
        ctx = _AsyncConnCtx(cur_fetch=lambda: None)
        create_conn_mock.return_value = ctx
        with self.assertRaises(RuntimeError):
            await create_referral_fulfillment(BASE)

    @patch("src.database.db.create_connection")
    @patch("src.database.db.time.sleep", return_value=None)
    async def test_exhausted_retries(self, _sleep, create_conn_mock):
        # cause execute to throw each time
        ctx = _AsyncConnCtx(cur_fetch=lambda: ["RID-X"])
        # override execute to always raise
        async def explode(*_a, **_k):
            raise RuntimeError("down")
        # patch after ctx creation
        ctx._cur.execute = AsyncMock(side_effect=explode)
        create_conn_mock.return_value = ctx
        with self.assertRaises(RuntimeError):
            await create_referral_fulfillment(BASE, retries=2)




##################################


import json
import unittest
from unittest.mock import patch, AsyncMock
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

class TestHandler(unittest.IsolatedAsyncioTestCase):
    def set_event(self, body):
        app._current_event = FakeEvent(body)  # type: ignore

    @patch("src.main.create_referral_fulfillment", new_callable=AsyncMock, return_value="123")
    async def test_201(self, _db):
        body = {
            "prospectAccountKey":"123",
            "prospectAccountKeyType":"CARD_ACCOUNT_ID",
            "sorId":"S",
            "referralReferenceKeys":[],
            "programCode":"PROGRAM_001",
            "referralCode":"REFERRAL_ABC",
        }
        self.set_event(body)
        res = await create_referral()
        self.assertEqual(res["statusCode"], 201)
        payload = json.loads(res["body"])
        self.assertEqual(payload["referralId"], "123")
        self.assertIn("/enterprise/referrals/123", res["headers"]["Location"])

    async def test_400_missing_body(self):
        app._current_event = FakeEvent(None)  # type: ignore
        res = await create_referral()
        self.assertEqual(res["statusCode"], 400)

    async def test_400_validation(self):
        self.set_event({"programCode":"BAD SPACE"})  # intentionally invalid/missing
        res = await create_referral()
        self.assertEqual(res["statusCode"], 400)

    @patch("src.main.create_referral_fulfillment", new_callable=AsyncMock, side_effect=RuntimeError("db down"))
    async def test_500_db(self, _db):
        body = {
            "prospectAccountKey":"123",
            "prospectAccountKeyType":"CARD_ACCOUNT_ID",
            "sorId":"S",
            "referralReferenceKeys":[],
            "programCode":"PROGRAM_001",
            "referralCode":"REFERRAL_ABC",
        }
        self.set_event(body)
        res = await create_referral()
        self.assertEqual(res["statusCode"], 500)





###############################


[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]
psycopg = {extras = ["binary"], version = ">=3.1,<3.3"}
psycopg_pool = ">=3.2,<3.3"
aws-lambda-powertools = ">=2.30,<3.0"
pydantic = ">=2.5,<3.0"

[dev-packages]
pytest = "*"
coverage = "*"

[requires]
python_version = "3.12"



###################################



AWSTemplateFormatVersion: '2010-09-09'
Description: Referrals Lambda (async psycopg3 + pool)

Parameters:
  FunctionName:
    Type: String
    Default: referrals-lambda
  DBUrl:
    Type: String
    Description: Postgres URL (jdbc:postgresql://.. or postgresql://..)
  DBUsername:
    Type: String
    Default: ""
  DBPassword:
    Type: String
    NoEcho: true
    Default: ""
  DBPoolMin:
    Type: Number
    Default: 1
  DBPoolMax:
    Type: Number
    Default: 5
  LogLevel:
    Type: String
    Default: INFO

Resources:
  ReferralsFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Ref FunctionName
      Handler: src.main.lambda_handler
      Runtime: python3.12
      Timeout: 30
      MemorySize: 512
      Environment:
        Variables:
          DB_URL: !Ref DBUrl
          DB_USERNAME: !Ref DBUsername
          DB_PASSWORD: !Ref DBPassword
          DB_POOL_MIN: !Ref DBPoolMin
          DB_POOL_MAX: !Ref DBPoolMax
          LOG_LEVEL: !Ref LogLevel
          POWERTOOLS_SERVICE_NAME: referrals
      Role: arn:aws:iam::123456789012:role/YourLambdaRole  # <-- replace
      Code:
        S3Bucket: your-artifacts-bucket                 # <-- replace
        S3Key: path/to/your/deployment.zip              # <-- replace

Outputs:
  FunctionArn:
    Value: !GetAtt ReferralsFunction.Arn



cd /path/to/your/repo/lambda \
&& export PATH="$HOME/.local/bin:$PATH" \
&& export PIPENV_VENV_IN_PROJECT=1 \
&& PY312="/opt/homebrew/opt/python@3.12/bin/python3.12" \
&& pipenv --python "$PY312" \
&& (pipenv sync --dev || pipenv install --dev) \
&& pipenv run python -c "import pydantic; print(pydantic.__version__)" \
&& export PYTHONPATH="$PWD/src" \
&& pipenv run pytest -q --cov=src --cov-report=term-missing
