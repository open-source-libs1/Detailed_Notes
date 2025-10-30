# after: body = CreateReferralEventInput(**app.current_event.json_body)

prospect = getattr(body, "prospect", None)
customer = getattr(body, "customer", None)

fulfillment = FulfillmentEvent(
    correlation_id=body.correlation_id,
    prospect_account_key=(getattr(prospect, "account_key", None) if prospect else None)
        or getattr(body, "prospect_account_key", None),
    prospect_account_key_type=(getattr(prospect, "account_key_type", None) if prospect else None)
        or getattr(body, "prospect_account_key_type", None),
    prospect_sor_id=(getattr(prospect, "sor_id", None) if prospect else None)
        or getattr(body, "prospect_sor_id", None),
    internal_program_key=getattr(body, "internal_program_key", None) or getattr(body, "program_key", None),
    referral_code=getattr(body, "referral_code", None),
    customer_fulfillment_reference_id=(getattr(customer, "fulfillment_reference_id", None) if customer else None)
        or getattr(body, "customer_fulfillment_reference_id", None),
    customer_fulfillment_reference_source_id=(getattr(customer, "fulfillment_reference_source_id", None) if customer else None)
        or getattr(body, "customer_fulfillment_reference_source_id", None),
    tenant_id=body.tenant_id,
    creation_user_id=getattr(body, "creation_user_id", None) or getattr(body, "created_by", None),
    last_updated_user_id=getattr(body, "last_updated_user_id", None) or getattr(body, "updated_by", None) or getattr(body, "creation_user_id", None),
    event_id=body.event_id,
)
