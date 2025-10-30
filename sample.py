
# src/models/fulfillment_event.py
from __future__ import annotations
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, conint

SmallInt = conint(ge=0, le=32767)

class FulfillmentEventCreate(BaseModel):
    """
    Pydantic schema for inserting into fulfillment_event.
    Only columns used by the INSERT ... RETURNING referral_code are modeled.
    """
    correlation_id: str = Field(..., description="Id to correlate upstream calls")
    prospect_account_key: Optional[str] = Field(None, description="Prospect account key")
    prospect_account_key_type: Optional[str] = Field(None, description="Type for prospect_account_key")
    prospect_sor_id: Optional[SmallInt] = Field(None, description="Prospect SOR id (smallint)")
    internal_program_key: int = Field(..., description="FK to program (bigint)")
    referral_code: str = Field(..., description="Referral code to persist/return")
    customer_fulfillment_reference_id: Optional[str] = Field(None, description="Customer fulfillment ref id")
    customer_fulfillment_reference_source_id: Optional[str] = Field(None, description="Source for the above id")
    tenant_id: SmallInt = Field(..., description="Tenant id (smallint)")
    creation_user_id: str = Field(..., description="Audit: created by")
    last_updated_user_id: str = Field(..., description="Audit: last updated by")
    event_id: UUID = Field(..., description="Event UUID from the request")

    def as_sql_params(self) -> tuple:
        """Column order must match the INSERT statement below."""
        return (
            self.correlation_id,
            self.prospect_account_key,
            self.prospect_account_key_type,
            self.prospect_sor_id,
            self.internal_program_key,
            self.referral_code,
            self.customer_fulfillment_reference_id,
            self.customer_fulfillment_reference_source_id,
            self.tenant_id,
            self.creation_user_id,
            self.last_updated_user_id,
            self.event_id,  # psycopg2 understands UUID objects
        )




###############################


# src/database/db.py  (add alongside your existing imports and logger)
import logging
from typing import Optional
from psycopg2.errors import UniqueViolation
from psycopg2.extensions import connection as PGConnection
from .models.fulfillment_event import FulfillmentEventCreate  # adjust import to your layout

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

INSERT_FULFILLMENT_EVENT_SQL = """
INSERT INTO fulfillment_event (
    correlation_id,
    prospect_account_key,
    prospect_account_key_type,
    prospect_sor_id,
    internal_program_key,
    referral_code,
    customer_fulfillment_reference_id,
    customer_fulfillment_reference_source_id,
    tenant_id,
    creation_user_id,
    last_updated_user_id,
    event_id
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING referral_code
""".strip()

def create_referral_event(conn: PGConnection, evt: FulfillmentEventCreate) -> str:
    """
    Insert one fulfillment_event row and return the referral_code.
    Follows the same pattern as other insert helpers: caller provides an open connection.
    """
    logger.info(
        "inserting fulfillment_event: correlation_id=%s, program_key=%s, tenant_id=%s, event_id=%s",
        evt.correlation_id, evt.internal_program_key, evt.tenant_id, evt.event_id
    )

    params = evt.as_sql_params()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(INSERT_FULFILLMENT_EVENT_SQL, params)
                row = cur.fetchone()
        if not row or row[0] is None:
            raise RuntimeError("INSERT fulfillment_event returned no referral_code")
        referral_code = str(row[0])
        logger.info("insert success: referral_code=%s", referral_code)
        return referral_code
    except UniqueViolation as e:
        # Surface clearly; upstream can decide whether to regenerate codes/retry.
        logger.warning("unique constraint violation on fulfillment_event: %s", e)
        raise
    except Exception as e:
        logger.error("insert failure for correlation_id=%s: %s", evt.correlation_id, e)
        raise




##################################


from __future__ import annotations

"""
Models + validation -> POST error mapping for createReferralEvent.
Lives with the POST contract on purpose (keeps main.py thin and patch-agnostic).
"""

import re
from typing import List

from pydantic import BaseModel, Field, field_validator, ValidationError

from src.api_specs.v1.error_response import ApiError
from src.error_codes import ErrorCode


class ReferralReferenceKey(BaseModel):
    """Single referral reference key item."""
    referralReferenceKeyName: str = Field(..., min_length=1, max_length=64)
    referralReferenceKeyValue: str = Field(..., min_length=1, max_length=128)


class CreateReferralEventInput(BaseModel):
    """Incoming POST body schema (validated here, not in main.py)."""
    prospectAccountKey: str = Field(..., min_length=1, max_length=64)
    prospectAccountKeyType: str = Field(..., min_length=1, max_length=64)
    sorId: str = Field(..., min_length=1, max_length=64)
    referralReferenceKeys: List[ReferralReferenceKey] = Field(default_factory=list)
    programCode: str = Field(..., min_length=1, max_length=64)
    referralCode: str = Field(..., min_length=1, max_length=64)

    @field_validator("prospectAccountKeyType")
    @classmethod
    def _v_account_key_type(cls, v: str) -> str:
        # Contract requires CARD_ACCOUNT_ID only.
        if v not in {"CARD_ACCOUNT_ID"}:
            # Keep this exact string — mapping relies on it.
            raise ValueError("Invalid account key type")
        return v

    @field_validator("referralCode")
    @classmethod
    def _v_referral_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v or ""):
            raise ValueError("Invalid referral code format")
        return v

    @field_validator("programCode")
    @classmethod
    def _v_program_code(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z0-9_]{3,64}", v or ""):
            raise ValueError("Invalid referral program code")
        return v


class CreateReferralEventOutput(BaseModel):
    """Success body (201)."""
    referralId: str


def map_create_validation_error(exc: ValidationError) -> ApiError:
    """
    Translate Pydantic ValidationError into API 400xx error contract used by POST.

    Coverage goals: all branches below are covered in tests:
    - Missing field -> 40001 (with field name)
    - Specific validators -> 40003/40004/40005
    - Fallback invalid -> 40002 (with offending field)
    """
    # Missing fields?
    for err in exc.errors():
        etype = (err.get("type") or "").lower()
        if etype == "missing" or etype.endswith("missing"):
            loc = ".".join(str(p) for p in err.get("loc", [])) or "field"
            return ApiError(
                **{
                    **ErrorCode.MISSING_REQUIRED_FIELD.to_dict(),
                    "developer_text": f"Missing required field in request ({loc})",
                }
            )

    # Our explicit validator messages (exact strings above)
    for err in exc.errors():
        msg = (err.get("msg") or "").strip()
        if "Invalid account key type" in msg:
            return ApiError(**ErrorCode.INVALID_ACCOUNT_KEY_TYPE.to_dict())
        if "Invalid referral code format" in msg:
            return ApiError(**ErrorCode.INVALID_REFERRAL_CODE_FORMAT.to_dict())
        if "Invalid referral program code" in msg:
            return ApiError(**ErrorCode.INVALID_PROGRAM_CODE.to_dict())

    # Generic invalid with field context
    first = (exc.errors() or [{}])[0]
    loc = ".".join(str(p) for p in first.get("loc", [])) or "field"
    return ApiError(
        **{
            **ErrorCode.INVALID_FIELD_VALUE.to_dict(),
            "developer_text": f"Invalid value for field ({loc})",
        }
    )



#######################


from enum import Enum


class ErrorCode(Enum):
    # POST /enterprise/referrals (400xx)
    MISSING_REQUIRED_FIELD = (40001, "Missing required field in request")
    INVALID_FIELD_VALUE = (40002, "Invalid value for field")
    INVALID_REFERRAL_CODE_FORMAT = (40003, "Invalid referral code format")
    INVALID_ACCOUNT_KEY_TYPE = (40004, "Invalid account key type")
    INVALID_PROGRAM_CODE = (40005, "Invalid referral program code")

    # Existing PATCH/health codes
    INVALID_REQUEST_FORMAT = (10001, "Invalid request format")
    REFERRAL_EVENT_NOT_FOUND = (10002, "Referral event does not exist")
    REFERRAL_EVENT_CANNOT_BE_UPDATED = (10003, "Referral event cannot be updated")
    INTERNAL_SERVER_ERROR = (10004, "Internal server error")
    ENDPOINT_DOES_NOT_EXIST = (10005, "Endpoint does not exist")

    def __init__(self, id: int, developer_text: str):
        self.id = id
        self.developer_text = developer_text

    def to_dict(self):
        return {"id": self.id, "developer_text": self.developer_text}




###########################



# ... keep your current imports above ...
from pydantic import ValidationError

# ⬇️ Import POST models + mapper (kept out of main.py by design)
from src.api_specs.v1.referral_event_create import (
    CreateReferralEventInput,
    CreateReferralEventOutput,
    map_create_validation_error,
)

# ... keep your existing logger/app/secrets/db_connection + PATCH endpoints ...


@app.post("/enterprise/referrals")
def create_referral_event():
    """
    Create a referral event using the same architectural pattern as PATCH:
    - Parse+validate via Pydantic
    - Map validation to 400xx using helper
    - On DB failure return 500
    - On success return 201 with { referralId }
    """
    logger.info("Creating referral event; request: %s", app.current_event.json_body)

    # 1) Validate body against POST schema.
    try:
        body = CreateReferralEventInput(**app.current_event.json_body)
    except ValidationError as e:
        logger.error("Bad request: %s", str(e))
        return Response(
            status_code=400,
            content_type="application/json",
            body=map_create_validation_error(e).model_dump(),
        )

    # 2) Insert using your db_util helper; return new referral_id.
    try:
        rid = create_fulfillment_event(
            db_connection,
            body.prospectAccountKey,
            body.prospectAccountKeyType,
            body.sorId,
            body.programCode,
            body.referralCode,
            [rk.model_dump() for rk in body.referralReferenceKeys],  # driver can ::jsonb it
        )
    except Exception as e:
        logger.exception("DB failure inserting referral event: %s", str(e))
        return Response(
            status_code=500,
            content_type="application/json",
            body=ApiError(**ErrorCode.INTERNAL_SERVER_ERROR.to_dict()).model_dump(),
        )

    # 3) Success (201) with only the referralId as per spec.
    return Response(
        status_code=201,
        content_type="application/json",
        body=CreateReferralEventOutput(referralId=str(rid)).model_dump(),
    )




#############################



import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Make `src` importable for this folder structure (matches your existing tests).
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# Patch import-time dependencies *before* importing main.py
with patch("boto3.client", return_value=MagicMock()) as _m_boto, \
     patch("aws_util.retrieve_secret_value",
           return_value="{'dbname':'d','username':'u','password':'p','host':'h','port':5432}") as _m_secret, \
     patch("db_util.create_connection", return_value=MagicMock()) as _m_conn:
    from src.main import app, create_referral_event  # noqa: E402

from unittest.mock import patch as upatch
from src.error_codes import ErrorCode


@pytest.fixture(scope="session", autouse=True)
def _stopall():
    # Ensure any global patches are released after the session
    yield
    patch.stopall()


# ---------- Happy path (201) ----------
@upatch("src.main.create_fulfillment_event", return_value="123")
def test_create_referral_201(_db):
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X", "referralReferenceKeyValue": "Y"}],
    })
    res = create_referral_event()
    assert res.status_code == 201
    assert res.body["referralId"] == "123"


# ---------- 400: Missing required (40001) ----------
def test_create_referral_400_missing_field():
    # programCode omitted
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "referralCode": "REF_001",
    })
    res = create_referral_event()
    assert res.status_code == 400
    assert res.body["id"] == ErrorCode.MISSING_REQUIRED_FIELD.id
    assert "programCode" in res.body["developer_text"]


# ---------- 400: Specific validators (40004 / 40005 / 40003) ----------
def test_create_referral_400_invalid_account_key_type():
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "BAD",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
    })
    res = create_referral_event()
    assert res.status_code == 400
    assert res.body["id"] == ErrorCode.INVALID_ACCOUNT_KEY_TYPE.id


def test_create_referral_400_invalid_program_code():
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "bad space",
        "referralCode": "REF_001",
    })
    res = create_referral_event()
    assert res.status_code == 400
    assert res.body["id"] == ErrorCode.INVALID_PROGRAM_CODE.id


def test_create_referral_400_invalid_referral_code():
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "bad space",
    })
    res = create_referral_event()
    assert res.status_code == 400
    assert res.body["id"] == ErrorCode.INVALID_REFERRAL_CODE_FORMAT.id


# ---------- 400: Generic invalid (40002) ----------
def test_create_referral_400_generic_invalid():
    # referralReferenceKeys must be a list, send wrong type to trigger generic branch
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
        "referralReferenceKeys": "not-a-list",
    })
    res = create_referral_event()
    assert res.status_code == 400
    assert res.body["id"] == ErrorCode.INVALID_FIELD_VALUE.id
    assert "referralReferenceKeys" in res.body["developer_text"]


# ---------- 500: DB failure ----------
@upatch("src.main.create_fulfillment_event", side_effect=Exception("db down"))
def test_create_referral_500(_db):
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
    })
    res = create_referral_event()
    assert res.status_code == 500
    assert res.body["id"] == ErrorCode.INTERNAL_SERVER_ERROR.id

