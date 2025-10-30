# db_util/schemas.py  (append or replace the previous full model)
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class FulfillmentEvent(BaseModel):
    """Complete schema for table fulfillment_event (all columns)."""

    # 1..8
    correlation_id: str = Field(..., max_length=512, description="varchar(512), NOT NULL")
    customer_account_key: Optional[str] = Field(None, max_length=64, description="varchar(64), NULL")
    customer_sor_id: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT, NULL")
    prospect_account_key: Optional[str] = Field(None, max_length=64, description="varchar(64), NULL")
    prospect_sor_id: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT, NULL")
    internal_program_key: Optional[int] = Field(None, description="BIGINT, NULL")
    referral_code: str = Field(..., max_length=16, description="varchar(16), NOT NULL")
    tenant_id: int = Field(..., ge=0, le=32767, description="SMALLINT, NOT NULL")

    # 9..16
    customer_fulfillment_status: Optional[str] = Field(None, max_length=8, description="varchar(8), NULL")
    prospect_fulfillment_status: Optional[str] = Field(None, max_length=8, description="varchar(8), NULL")
    customer_fulfillment_eligibility_reason: Optional[str] = Field(None, description="varchar, NULL")
    prospect_fulfillment_eligibility_reason: Optional[str] = Field(None, description="varchar, NULL")
    customer_fulfilled_amount: Optional[Decimal] = Field(None, description="numeric, NULL")
    prospect_fulfilled_amount: Optional[Decimal] = Field(None, description="numeric, NULL")
    customer_fulfillment_date: Optional[date] = Field(None, description="date, NULL")
    prospect_fulfillment_date: Optional[date] = Field(None, description="date, NULL")

    # 17..22
    customer_retry_count: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT, NULL")
    prospect_retry_count: Optional[int] = Field(None, ge=0, le=32767, description="SMALLINT, NULL")
    customer_fulfillment_reference_id: Optional[str] = Field(None, description="varchar, NULL")
    customer_fulfillment_reference_source_id: Optional[str] = Field(None, description="varchar, NULL")
    prospect_fulfillment_reference_id: Optional[str] = Field(None, description="varchar, NULL")
    prospect_fulfillment_reference_source_id: Optional[str] = Field(None, description="varchar, NULL")

    # 23..29
    creation_timestamp: Optional[datetime] = Field(None, description="timestamp, default now()")
    creation_user_id: str = Field(..., description="varchar, NOT NULL")
    last_updated_timestamp: Optional[datetime] = Field(None, description="timestamp, default now()")
    last_updated_user_id: str = Field(..., description="varchar, NOT NULL")
    event_id: UUID = Field(..., description="uuid, NOT NULL")
    customer_account_key_type: Optional[str] = Field(None, description="varchar, NULL")
    prospect_account_key_type: Optional[str] = Field(None, description="varchar, NULL")
