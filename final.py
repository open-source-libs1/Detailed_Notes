# --- db_util/schemas.py (append this) ---
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class FulfillmentEvent(BaseModel):
    """
    Full row model for fulfillment_event (all columns).
    Nullable columns -> Optional[...] with default None.
    Non-nullable columns -> required (no default).
    SMALLINT columns use ge/le bounds; BIGINT stays as int (no bounds per request).
    """

    # 1..8
    correlation_id: str = Field(..., max_length=512, description="NOT NULL")
    customer_account_key: Optional[str] = Field(None, max_length=64)
    customer_sor_id: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT")
    prospect_account_key: Optional[str] = Field(None, max_length=64)
    prospect_sor_id: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT")
    internal_program_key: Optional[int] = Field(None, description="BIGINT")
    referral_code: str = Field(..., max_length=16, description="NOT NULL")
    tenant_id: int = Field(..., ge=0, le=32767, description="SMALLINT NOT NULL")

    # 9..16
    customer_fulfillment_status: Optional[str] = Field(None, max_length=8)
    prospect_fulfillment_status: Optional[str] = Field(None, max_length=8)
    customer_fulfillment_eligibility_reason: Optional[str] = None
    prospect_fulfillment_eligibility_reason: Optional[str] = None
    customer_fulfilled_amount: Optional[Decimal] = None
    prospect_fulfilled_amount: Optional[Decimal] = None
    customer_fulfillment_date: Optional[date] = None
    prospect_fulfillment_date: Optional[date] = None

    # 17..22
    customer_retry_count: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT")
    prospect_retry_count: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT")
    customer_fulfillment_reference_id: Optional[str] = None
    customer_fulfillment_reference_source_id: Optional[str] = None
    prospect_fulfillment_reference_id: Optional[str] = None
    prospect_fulfillment_reference_source_id: Optional[str] = None

    # 23..29
    creation_timestamp: Optional[datetime] = Field(
        None, description="timestamp, default now() in DB"
    )
    creation_user_id: str = Field(..., description="NOT NULL")
    last_updated_timestamp: Optional[datetime] = Field(
        None, description="timestamp, default now() in DB"
    )
    last_updated_user_id: str = Field(..., description="NOT NULL")
    event_id: UUID = Field(..., description="uuid, NOT NULL")
    customer_account_key_type: Optional[str] = None
    prospect_account_key_type: Optional[str] = None
