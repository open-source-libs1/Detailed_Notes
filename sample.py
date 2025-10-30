# tests/test_post.py
import os, sys, pytest
from unittest.mock import MagicMock, patch as upatch

# ... your existing sys.path + global patches remain ...

TEST_EVENT_ID = "123e4567-e89b-12d3-a456-426614174000"   # valid UUID string

def _set_event(payload: dict):
    evt = MagicMock(json_body=payload)
    # optional: header only used for logging; safe to add
    evt.headers = {"x-amzn-trace-id": f"Root=1-65a7b3c1-{TEST_EVENT_ID}"}
    return evt

@upatch("src.main.insert_fulfillment_event", return_value="123")
def test_create_referral_201_db(_mock):
    from src.main import app, create_referral_event

    app.current_event = _set_event({
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "123",
        "programCode": "987",
        "referralCode": "REF_001",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X",
                                   "referralReferenceKeyValue": "Y"}],
    })
    # **critical**: make aws_request_id a real UUID string
    app.lambda_context = MagicMock(aws_request_id=TEST_EVENT_ID)

    res = create_referral_event()
    assert res.status_code == 201
    assert res.body["referralId"] == "123"

@upatch("src.main.insert_fulfillment_event", side_effect=Exception("db down"))
def test_create_referral_500(_mock):
    from src.main import app, create_referral_event

    app.current_event = _set_event({
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "123",
        "programCode": "987",
        "referralCode": "REF_001",
    })
    app.lambda_context = MagicMock(aws_request_id=TEST_EVENT_ID)

    res = create_referral_event()
    assert res.status_code == 500
    assert res.body["id"] == ErrorCode.INTERNAL_SERVER_ERROR.id
