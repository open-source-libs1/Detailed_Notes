
# src/models/fulfillment_event.py
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class FulfillmentEventCreate(BaseModel):
    correlation_id: str = Field(...)
    prospect_account_key: Optional[str] = Field(None)
    prospect_account_key_type: Optional[str] = Field(None)
    prospect_sor_id: Optional[int] = Field(None, ge=0, le=32767)   # SMALLINT
    internal_program_key: int = Field(...)                         # BIGINT (keep plain int)
    referral_code: str = Field(...)
    customer_fulfillment_reference_id: Optional[str] = Field(None)
    customer_fulfillment_reference_source_id: Optional[str] = Field(None)
    tenant_id: int = Field(..., ge=0, le=32767)                    # SMALLINT
    creation_user_id: str = Field(...)
    last_updated_user_id: str = Field(...)
    event_id: UUID = Field(...)
