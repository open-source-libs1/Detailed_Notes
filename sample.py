


_SQL = """
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
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING referral_code;
""".strip()


################################


from uuid import uuid4
from typing import Dict, Any

@app.post("/enterprise/referrals")
def create_referral() -> Dict[str, Any]:
    # 1) Parse body
    try:
        body = app.current_event.json_body or {}
    except Exception:
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=40001, developerText="Missing required field in request"))

    # 1a) Get event_id from Lambda context (fallbacks if not running in Lambda)
    event_id = (
        getattr(app.lambda_context, "aws_request_id", None) or
        (getattr(app.current_event, "request_context", {}) or {}).get("requestId") or
        str(uuid4())
    )

    # 2) Validate
    try:
        req = ReferralCreateRequest.model_validate(body)
    except Exception as e:
        code, message = map_validation_to_400xx(e)
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=code, developerText=message))

    # 3) DB insert (pass event_id)
    try:
        rid = create_referral_fulfillment(req.model_dump(), event_id)
    except Exception:
        logger.exception("db failure")
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorBody(id=50000, developerText="db failure"))

    # 4) Log + respond (unchanged)
    created_at = datetime.now(timezone.utc).isoformat()
    path = f"/enterprise/referrals/{rid}"
    logger.info(f"referral created referralId={rid} createdAt={created_at} path={path}")
    return _resp(HTTPStatus.CREATED, {"referralId": rid, "createdAt": created_at, "path": path})
