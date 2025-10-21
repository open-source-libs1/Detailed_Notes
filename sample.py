from pydantic import ValidationError  # add this import

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
        # ✅ v2-friendly: always run full validation on a dict
        req = ReferralCreateRequest.model_validate(body)
    except Exception as e:  # or except ValidationError as e:
        code, message = map_validation_to_400xx(e)
        return _resp(HTTPStatus.BAD_REQUEST, ErrorBody(id=code, developerText=message).model_dump())

    try:
        rid = await create_referral_fulfillment(req.model_dump())
    except Exception:
        logger.exception("db failure")
        return _resp(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            ErrorBody(id=50000, developerText="Internal Server Error").model_dump()
        )

    host = app.current_event.headers.get("host", "")
    proto = app.current_event.headers.get("x-forwarded-proto", "https")
    location = f"{proto}://{host}/enterprise/referrals/{rid}" if host else f"/enterprise/referrals/{rid}"
    return _resp(HTTPStatus.CREATED, ReferralCreateResponse(referralId=rid).model_dump(),
                 headers={"Location": location})



PIPENV_IGNORE_VIRTUALENVS=1 pipenv sync --dev
pipenv run pytest --maxfail=1 --disable-warnings --cov=src --cov-report=term-missing -q


pipenv run pytest --maxfail=1 --disable-warnings --cov=src --cov-report=term-missing -q

