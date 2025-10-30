# src/main.py
from pydantic import ValidationError
import re, uuid

@app.post("/enterprise/referrals")
def create_referral_event():
    logger.info("Creating referral event; request: %s", app.current_event.json_body)

    # Validate body
    try:
        body = CreateReferralEventInput(**app.current_event.json_body)
    except ValidationError as e:
        logger.error("Bad request: %s", str(e))
        return Response(
            status_code=400,
            content_type="application/json",
            body=map_create_validation_error(e).model_dump(),
        )

    # Use dict, not the model itself
    payload = body.model_dump()

    # Optional inner keys
    keys = payload.get("referralReferenceKeys") or []
    first = keys[0] if keys and isinstance(keys[0], dict) else {}
    referralReferenceKeyName = first.get("referralReferenceKeyName")
    referralReferenceKeyValue = first.get("referralReferenceKeyValue")

    # Defaults
    tenant_id = 1
    created_user = last_user = "fulfillment-lambda"

    # event_id & correlation_id – safe in tests (no lambda_context)
    ctx = getattr(app, "lambda_context", None)
    event_id = getattr(ctx, "aws_request_id", None)
    if not event_id:
        hdrs = getattr(getattr(app, "current_event", None), "headers", {}) or {}
        event_id = hdrs.get("x-amzn-trace-id") or hdrs.get("X-Amzn-Trace-Id") or uuid.uuid4().hex
    correlation_id = re.sub(r"[^0-9A-Za-z]", "", str(event_id))[:8] or uuid.uuid4().hex[:8]

    # Build ORM/DTO
    fulfillment = FulfillmentEvent(
        correlation_id=correlation_id,
        prospect_account_key=payload["prospectAccountKey"],
        prospect_account_key_type=payload["prospectAccountKeyType"],
        prospect_sor_id=payload["sorId"],
        internal_program_key=payload["programCode"],
        referral_code=payload["referralCode"],
        customer_fulfillment_reference_id=referralReferenceKeyName,
        customer_fulfillment_reference_source_id=referralReferenceKeyValue,
        tenant_id=tenant_id,
        creation_user_id=created_user,
        last_updated_user_id=last_user,
        event_id=event_id,
    )

    # Insert & respond
    try:
        event_id = insert_fulfillment_event(db_connection, fulfillment)
    except Exception as e:
        logger.exception("DB failure inserting referral event: %s", str(e))
        return Response(
            status_code=500,
            content_type="application/json",
            body=ApiError(**ErrorCode.INTERNAL_SERVER_ERROR.to_dict()).model_dump(),
        )

    return Response(
        status_code=201,
        content_type="application/json",
        body=CreateReferralEventOutput(referralId=str(event_id)).model_dump(),
    )
