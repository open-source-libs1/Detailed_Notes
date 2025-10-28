# tests/test_main.py
import json
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch

from src.main import lambda_handler


def _alb_event(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    return {
        "httpMethod": method,
        "path": path,
        "isBase64Encoded": False,
        "headers": {
            "content-type": "application/json",
            "x-forwarded-proto": "https",
            "host": "example.com",
            **(headers or {}),
        },
        "queryStringParameters": None,
        "requestContext": {"elb": {"targetGroupArn": "arn:aws:elasticloadbalancing:..."}},
        "body": None if body is None else json.dumps(body),
    }


def _ctx():
    # Minimal LambdaContext stub so aws-lambda-powertools logger doesn't crash
    return SimpleNamespace(
        function_name="fn",
        memory_limit_in_mb=128,
        invoked_function_arn="arn:aws:lambda:us-east-1:123:function:fn",
        aws_request_id="req-123",
    )


def test_health():
    ev = _alb_event("GET", "/referrals/health")
    res = lambda_handler(ev, _ctx())
    assert res["statusCode"] == 200
    payload = json.loads(res["body"])
    assert payload["status"] == "healthy"


@patch("src.main.create_referral_fulfillment", return_value="123")
def test_create_referral_201(_mock_db):
    body = {
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
        "referralReferenceKeys": [],
    }
    ev = _alb_event("POST", "/enterprise/referrals", body=body)
    res = lambda_handler(ev, _ctx())
    assert res["statusCode"] == HTTPStatus.CREATED
    assert json.loads(res["body"]) == {"referralId": "123"}


def test_create_referral_400_missing_body():
    # Non-JSON / missing body -> 40001
    ev = _alb_event(
        "POST",
        "/enterprise/referrals",
        body=None,
        headers={"content-type": "text/plain"},
    )
    res = lambda_handler(ev, _ctx())
    assert res["statusCode"] == HTTPStatus.BAD_REQUEST
    body = json.loads(res["body"])
    assert body["id"] == 40001


def test_create_referral_400_validation_error():
    # Missing required programCode -> 40001
    bad = {
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "referralCode": "REF_001",
    }
    ev = _alb_event("POST", "/enterprise/referrals", body=bad)
    res = lambda_handler(ev, _ctx())
    assert res["statusCode"] == HTTPStatus.BAD_REQUEST
    assert json.loads(res["body"])["id"] == 40001


@patch("src.main.create_referral_fulfillment", side_effect=RuntimeError("db down"))
def test_create_referral_500(_mock_db):
    good = {
        "prospectAccountKey": "123",
        "prospectAccountKeyType": "CARD_ACCOUNT_ID",
        "sorId": "S1",
        "programCode": "PROG_001",
        "referralCode": "REF_001",
    }
    ev = _alb_event("POST", "/enterprise/referrals", body=good)
    res = lambda_handler(ev, _ctx())
    assert res["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert json.loads(res["body"])["id"] == 50000


def test_update_referral_204():
    ev = _alb_event("PATCH", "/enterprise/referrals/abc", body={"x": 1})
    res = lambda_handler(ev, _ctx())
    assert res["statusCode"] == 204


def test_not_found_404():
    ev = _alb_event("GET", "/nope")
    res = lambda_handler(ev, _ctx())
    assert res["statusCode"] == 404
