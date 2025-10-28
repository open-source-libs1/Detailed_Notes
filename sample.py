


# tests/test_model.py
import pytest
from pydantic import ValidationError

from src.models.model_referral import (
    ReferralCreateRequest,
    ReferralReferenceKey,
    ReferralCreateResponse,
    ErrorBody,
    BadRequest,
    map_validation_to_400xx,
)


def _good_payload(**overrides):
    base = {
        "prospectAccountKey": "123456789",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "SOR1",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X", "referralReferenceKeyValue": "Y"}],
        "programCode": "PROGRAM_001",
        "referralCode": "REF_001",
    }
    base.update(overrides)
    return base


def test_valid_request_roundtrip():
    req = ReferralCreateRequest.model_validate(_good_payload())
    dumped = req.model_dump()
    assert dumped["programCode"] == "PROGRAM_001"
    assert dumped["referralCode"] == "REF_001"
    # simple models
    resp = ReferralCreateResponse(referralId="42")
    err = ErrorBody(id=40001, developerText="x")
    assert resp.referralId == "42" and err.id == 40001


def test_missing_field_maps_40001():
    bad = _good_payload()
    bad.pop("programCode")
    with pytest.raises(ValidationError) as e:
        ReferralCreateRequest.model_validate(bad)
    code, msg = map_validation_to_400xx(e.value)
    assert code == 40001
    assert "Missing required field" in msg


def test_invalid_account_key_type_maps_40004():
    bad = _good_payload(prospectAccountKeyType="NOT_ALLOWED")
    with pytest.raises(Exception) as e:
        ReferralCreateRequest.model_validate(bad)
    code, msg = map_validation_to_400xx(e.value)
    assert code == 40004
    assert "account key type" in msg


def test_invalid_referral_code_maps_40003():
    bad = _good_payload(referralCode="bad space")
    with pytest.raises(Exception) as e:
        ReferralCreateRequest.model_validate(bad)
    code, _ = map_validation_to_400xx(e.value)
    assert code == 40003


def test_invalid_program_code_maps_40005():
    bad = _good_payload(programCode="bad space")
    with pytest.raises(Exception) as e:
        ReferralCreateRequest.model_validate(bad)
    code, _ = map_validation_to_400xx(e.value)
    assert code == 40005


def test_generic_invalid_maps_40002():
    # Wrong type for referralReferenceKeys -> generic invalid
    bad = _good_payload(referralReferenceKeys="not-a-list")
    with pytest.raises(ValidationError) as e:
        ReferralCreateRequest.model_validate(bad)
    code, _ = map_validation_to_400xx(e.value)
    assert code == 40002


def test_map_validation_passthrough_for_badrequest():
    exc = BadRequest(40005, "Invalid referral program code")
    code, msg = map_validation_to_400xx(exc)
    assert code == 40005
    assert "program" in msg.lower()


def test_referral_reference_key_model_valid_and_invalid():
    ok = ReferralReferenceKey(referralReferenceKeyName="A", referralReferenceKeyValue="B")
    assert ok.referralReferenceKeyName == "A"
    # too short -> pydantic error -> generic 40002
    with pytest.raises(ValidationError) as e:
        ReferralReferenceKey(referralReferenceKeyName="", referralReferenceKeyValue="B")
    code, _ = map_validation_to_400xx(e.value)
    assert code == 40002
