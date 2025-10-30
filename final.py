# db_util/schemas.py
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class FulfillmentEvent(BaseModel):
    """Complete schema for table `fulfillment_event` (all columns)."""

    # 1..8
    correlation_id: str = Field(
        ..., max_length=512,
        description="Correlation identifier linking upstream requests (varchar(512), NOT NULL).",
    )
    customer_account_key: Optional[str] = Field(
        None, max_length=64,
        description="Customer account business key (varchar(64), NULL).",
    )
    customer_sor_id: Optional[int] = Field(
        None, ge=0, le=32767,
        description="Customer System-of-Record id (SMALLINT 0–32767, NULL).",
    )
    prospect_account_key: Optional[str] = Field(
        None, max_length=64,
        description="Prospect account business key (varchar(64), NULL).",
    )
    prospect_sor_id: Optional[int] = Field(
        None, ge=0, le=32767,
        description="Prospect System-of-Record id (SMALLINT 0–32767, NULL).",
    )
    internal_program_key: Optional[int] = Field(
        None,
        description="Program primary key (BIGINT, FK to program, NULL).",
    )
    referral_code: str = Field(
        ..., max_length=16,
        description="Referral code persisted and returned to caller (varchar(16), NOT NULL).",
    )
    tenant_id: int = Field(
        ..., ge=0, le=32767,
        description="Tenant identifier (SMALLINT 0–32767, NOT NULL).",
    )

    # 9..16
    customer_fulfillment_status: Optional[str] = Field(
        None, max_length=8,
        description="Latest customer fulfillment status (varchar(8), NULL).",
    )
    prospect_fulfillment_status: Optional[str] = Field(
        None, max_length=8,
        description="Latest prospect fulfillment status (varchar(8), NULL).",
    )
    customer_fulfillment_eligibility_reason: Optional[str] = Field(
        None,
        description="Why the customer qualified/failed eligibility (text, NULL).",
    )
    prospect_fulfillment_eligibility_reason: Optional[str] = Field(
        None,
        description="Why the prospect qualified/failed eligibility (text, NULL).",
    )
    customer_fulfilled_amount: Optional[Decimal] = Field(
        None,
        description="Amount credited/paid to customer (numeric, NULL).",
    )
    prospect_fulfilled_amount: Optional[Decimal] = Field(
        None,
        description="Amount credited/paid to prospect (numeric, NULL).",
    )
    customer_fulfillment_date: Optional[date] = Field(
        None,
        description="Calendar date of customer fulfillment (date, NULL).",
    )
    prospect_fulfillment_date: Optional[date] = Field(
        None,
        description="Calendar date of prospect fulfillment (date, NULL).",
    )

    # 17..22
    customer_retry_count: Optional[int] = Field(
        None, ge=0, le=32767,
        description="Number of retry attempts for customer (SMALLINT 0–32767, NULL).",
    )
    prospect_retry_count: Optional[int] = Field(
        None, ge=0, le=32767,
        description="Number of retry attempts for prospect (SMALLINT 0–32767, NULL).",
    )
    customer_fulfillment_reference_id: Optional[str] = Field(
        None,
        description="External reference id for customer fulfillment (e.g., coupon/txn id) (varchar, NULL).",
    )
    customer_fulfillment_reference_source_id: Optional[str] = Field(
        None,
        description="Source system for customer_fulfillment_reference_id (varchar, NULL).",
    )
    prospect_fulfillment_reference_id: Optional[str] = Field(
        None,
        description="External reference id for prospect fulfillment (varchar, NULL).",
    )
    prospect_fulfillment_reference_source_id: Optional[str] = Field(
        None,
        description="Source system for prospect_fulfillment_reference_id (varchar, NULL).",
    )

    # 23..29
    creation_timestamp: Optional[datetime] = Field(
        None,
        description="Record creation timestamp; database default `now()` (timestamp without time zone, NULL on insert).",
    )
    creation_user_id: str = Field(
        ...,
        description="User/service that created the record (varchar, NOT NULL).",
    )
    last_updated_timestamp: Optional[datetime] = Field(
        None,
        description="Record last update timestamp; database default `now()` (timestamp without time zone, NULL on insert).",
    )
    last_updated_user_id: str = Field(
        ...,
        description="User/service that last updated the record (varchar, NOT NULL).",
    )
    event_id: UUID = Field(
        ...,
        description="Upstream event identifier (uuid, NOT NULL).",
    )
    customer_account_key_type: Optional[str] = Field(
        None,
        description="Type/classifier for customer_account_key (e.g., CRM, SFDC) (varchar, NULL).",
    )
    prospect_account_key_type: Optional[str] = Field(
        None,
        description="Type/classifier for prospect_account_key (varchar, NULL).",
    )
