# Happy path
@upatch("src.main.insert_fulfillment_event", return_value="123")
def test_create_referral_201_db(_mock):
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
        "referralReferenceKeys": [{"referralReferenceKeyName": "X", "referralReferenceKeyValue": "Y"}],
    })
    res = create_referral_event()
    assert res.status_code == 201
    assert res.body["referralId"] == "123"

# 500 path
@upatch("src.main.insert_fulfillment_event", side_effect=Exception("db down"))
def test_create_referral_500(_mock):
    app.current_event = MagicMock(json_body={
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
    })
    res = create_referral_event()
    assert res.status_code == 500
    assert res.body["id"] == ErrorCode.INTERNAL_SERVER_ERROR.id
