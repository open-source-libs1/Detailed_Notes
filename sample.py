@upatch("src.main.get_account_enrollment_data", return_value=None)
def test_create_referral_400_invalid_referral_or_program(_mock_enroll):
    # keep event schema valid so we reach the enrollment_data branch
    app.current_event = _set_event({
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "123",
        "programCode": "987",
        "referralCode": "REF_001",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X", "referralReferenceKeyValue": "Y"}],
    })
    app.lambda_context = MagicMock(aws_request_id=TEST_EVENT_ID)

    res = create_referral_event()

    assert res.status_code == 400
    assert res.body["id"] == ErrorCode.REFERRAL_DATA_INVALID.id


@upatch("src.main.get_account_enrollment_data", return_value={"account_id": "123", "tenant_id": 2, "sor_id": 1, "is_active": True})
@upatch("src.main.insert_fulfillment_event", return_value="123")
def test_create_referral_201_tenant2_db(_mock_insert, _mock_enroll):
    # tenant_id == 2 should hit: TOKENIZED_BANK_ACCOUNT_NUMBER branch
    app.current_event = _set_event({
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "123",
        "programCode": "987",
        "referralCode": "REF_001",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X", "referralReferenceKeyValue": "Y"}],
    })
    app.lambda_context = MagicMock(aws_request_id=TEST_EVENT_ID)

    res = create_referral_event()

    assert res.status_code == 201
    assert res.body["referralId"] == "123"


@upatch("src.main.get_account_enrollment_data", return_value={"account_id": "123", "tenant_id": 999, "sor_id": 1, "is_active": True})
@upatch("src.main.insert_fulfillment_event")
def test_create_referral_500_invalid_tenant_id(_mock_insert, _mock_enroll):
    # tenant_id not in (1,2) should return INTERNAL_SERVER_ERROR
    app.current_event = _set_event({
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "123",
        "programCode": "987",
        "referralCode": "REF_001",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X", "referralReferenceKeyValue": "Y"}],
    })
    app.lambda_context = MagicMock(aws_request_id=TEST_EVENT_ID)

    res = create_referral_event()

    assert res.status_code == 500
    assert res.body["id"] == ErrorCode.INTERNAL_SERVER_ERROR.id
    _mock_insert.assert_not_called()
