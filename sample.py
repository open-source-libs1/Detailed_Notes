@app.post("/enterprise/referrals")
def create_referral() -> Dict[str, Any]:
    body = app.current_event.json_body or {}
    req = ReferralCreateRequest.model_validate(body)

    event_id = app.lambda_context.aws_request_id                 # UUID string
    correlation_id = app.current_event.request_context["requestId"]  # from context

    rid = create_referral_fulfillment(req.model_dump(), event_id, correlation_id)

    created_at = datetime.now(timezone.utc).isoformat()
    path = f"/enterprise/referrals/{rid}"
    return _resp(HTTPStatus.CREATED, {"referralId": rid, "createdAt": created_at, "path": path})
