from datetime import date, datetime
import os
import boto3
from aws_lambda_powertools import Logger

from aws_util import push_records_to_kinesis
from db_util import get_fulfillment_event_for_onestream
from onestream_util import CustomerReferralsFulfillmentActivityV1

logger = Logger(service="FulfillmentApi", child=True)
kinesis = boto3.client("kinesis")


def _fetch_data(connection, event_id: str, data: dict | None) -> dict | None:
    if data:
        return data

    try:
        data = get_fulfillment_event_for_onestream(connection, event_id)
    except Exception as e:
        logger.error("Failed to get fulfillment event for OneStream: %s", str(e))
        return None

    if not data:
        logger.error("No data found for event ID: %s", event_id)
        return None

    return data


def _map_to_schema(data: dict, event_id: str) -> CustomerReferralsFulfillmentActivityV1 | None:
    try:
        data["referral_event_id"] = data.get("event_id", event_id)
        data["origination_correlation_id"] = data.get("correlation_id")
        data["origination_tenant_id"] = data.get("tenant_id")
        data["creation_utc_timestamp"] = data.get("creation_timestamp")
        data["last_updated_utc_timestamp"] = data.get("last_updated_timestamp")
        return CustomerReferralsFulfillmentActivityV1(**data)
    except Exception as e:
        logger.error("Failed to map to OneStream schema: %s", str(e))
        return None


def _build_onestream_payload(schema_obj: CustomerReferralsFulfillmentActivityV1) -> dict:
    domain_payload = (
        CustomerReferralsFulfillmentActivityV1.model_validate(schema_obj)
        .model_dump(exclude_none=True)
    )

    # Normalize date/datetime to isoformat
    if isinstance(domain_payload.get("creation_utc_timestamp"), datetime):
        domain_payload["creation_utc_timestamp"] = domain_payload["creation_utc_timestamp"].isoformat(
            sep=" ", timespec="milliseconds"
        )
    if isinstance(domain_payload.get("last_updated_utc_timestamp"), datetime):
        domain_payload["last_updated_utc_timestamp"] = domain_payload["last_updated_utc_timestamp"].isoformat(
            sep=" ", timespec="milliseconds"
        )
    if isinstance(domain_payload.get("customer_fulfillment_date"), date):
        domain_payload["customer_fulfillment_date"] = domain_payload["customer_fulfillment_date"].isoformat()
    if isinstance(domain_payload.get("prospect_fulfillment_date"), date):
        domain_payload["prospect_fulfillment_date"] = domain_payload["prospect_fulfillment_date"].isoformat()

    # Normalize amounts to string
    if "customer_fulfilled_amount" in domain_payload:
        domain_payload["customer_fulfilled_amount"] = str(domain_payload["customer_fulfilled_amount"])
    if "prospect_fulfilled_amount" in domain_payload:
        domain_payload["prospect_fulfilled_amount"] = str(domain_payload["prospect_fulfilled_amount"])

    return {
        "schemaName": os.environ.get("ONESTREAM_SCHEMA_NAME", "customer_referral_fulfillment_activity"),
        "domainPayload": domain_payload,
    }


def send_fulfillment_to_onestream(connection, event_id: str, data: dict | None = None):  # type: ignore
    data = _fetch_data(connection, event_id, data)
    if not data:
        return

    schema_obj = _map_to_schema(data, event_id)
    if not schema_obj:
        return

    try:
        onestream_payload = _build_onestream_payload(schema_obj)
        push_records_to_kinesis(
            kinesis,
            os.environ.get("ONESTREAM_KINESIS_STREAM_ARN"),
            [onestream_payload],
        )
        logger.info("Successfully pushed to OneStream Kinesis stream: %s", [onestream_payload])
    except Exception as e:
        logger.error("Failed to push to OneStream Kinesis stream: %s", str(e))
        return





//////////////////////////////////

# tests/test_onestream.py
import os
import importlib
from datetime import datetime, date
from unittest.mock import MagicMock, patch

import pytest


# ---- Module import (avoid real boto3 client creation at import-time) ----
@pytest.fixture(scope="module")
def onestream_module():
    with patch("boto3.client") as mock_boto_client:
        mock_boto_client.return_value = MagicMock(name="mock_kinesis_client")
        from src import onestream as m  # <-- adjust if your package path differs
        importlib.reload(m)  # ensure patched boto3.client is applied
        return m


# -------------------- Helper tests --------------------

def test_fetch_data_uses_given_data(onestream_module):
    conn = MagicMock()
    data_in = {"event_id": "123"}
    out = onestream_module._fetch_data(conn, "123", data_in)
    assert out == data_in


def test_fetch_data_calls_db_when_data_missing(onestream_module):
    conn = MagicMock()
    with patch.object(onestream_module, "get_fulfillment_event_for_onestream") as mock_get:
        mock_get.return_value = {"event_id": "123"}
        out = onestream_module._fetch_data(conn, "123", None)
        mock_get.assert_called_once_with(conn, "123")
        assert out == {"event_id": "123"}


def test_fetch_data_returns_none_when_db_returns_empty(onestream_module):
    conn = MagicMock()
    with patch.object(onestream_module, "get_fulfillment_event_for_onestream") as mock_get:
        mock_get.return_value = None
        out = onestream_module._fetch_data(conn, "123", None)
        assert out is None


def test_map_to_schema_success(onestream_module):
    # Mock the Pydantic class constructor
    with patch.object(onestream_module, "CustomerReferralsFulfillmentActivityV1") as mock_schema:
        mock_schema.return_value = MagicMock(name="schema_obj")
        data = {
            "event_id": "E1",
            "correlation_id": "C1",
            "tenant_id": "T1",
            "creation_timestamp": "2023-10-01T12:00:00Z",
            "last_updated_timestamp": "2023-10-01T13:00:00Z",
        }
        schema_obj = onestream_module._map_to_schema(data, event_id="E1")
        assert schema_obj is mock_schema.return_value

        # Ensure remaps happened (inputs to schema constructor)
        kwargs = mock_schema.call_args.kwargs
        assert kwargs["referral_event_id"] == "E1"
        assert kwargs["origination_correlation_id"] == "C1"
        assert kwargs["origination_tenant_id"] == "T1"
        assert kwargs["creation_utc_timestamp"] == "2023-10-01T12:00:00Z"
        assert kwargs["last_updated_utc_timestamp"] == "2023-10-01T13:00:00Z"


def test_map_to_schema_returns_none_on_exception(onestream_module):
    with patch.object(onestream_module, "CustomerReferralsFulfillmentActivityV1") as mock_schema:
        mock_schema.side_effect = Exception("boom")
        out = onestream_module._map_to_schema({"event_id": "E1"}, event_id="E1")
        assert out is None


def test_build_onestream_payload_normalizes_types(onestream_module, monkeypatch):
    monkeypatch.setenv("ONESTREAM_SCHEMA_NAME", "test_schema")

    # Build a fake schema object, and mock model_validate/model_dump chain
    fake_schema_obj = MagicMock(name="schema_obj")

    with patch.object(onestream_module, "CustomerReferralsFulfillmentActivityV1") as mock_schema_cls:
        mock_schema_cls.model_validate.return_value = MagicMock(
            model_dump=MagicMock(
                return_value={
                    "creation_utc_timestamp": datetime(2023, 10, 1, 12, 0, 0),
                    "last_updated_utc_timestamp": datetime(2023, 10, 1, 12, 1, 0),
                    "customer_fulfillment_date": date(2023, 10, 1),
                    "prospect_fulfillment_date": date(2023, 10, 2),
                    "customer_fulfilled_amount": 12.34,
                    "prospect_fulfilled_amount": 56.78,
                }
            )
        )

        payload = onestream_module._build_onestream_payload(fake_schema_obj)

    assert payload["schemaName"] == "test_schema"
    dp = payload["domainPayload"]
    assert isinstance(dp["creation_utc_timestamp"], str)
    assert isinstance(dp["last_updated_utc_timestamp"], str)
    assert dp["customer_fulfillment_date"] == "2023-10-01"
    assert dp["prospect_fulfillment_date"] == "2023-10-02"
    assert dp["customer_fulfilled_amount"] == "12.34"
    assert dp["prospect_fulfilled_amount"] == "56.78"


# -------------------- Main function behavior tests --------------------

@patch.dict(os.environ, {"ONESTREAM_SCHEMA_NAME": "test_schema", "ONESTREAM_KINESIS_STREAM_ARN": "arn:test"})
def test_send_fulfillment_with_data_success(onestream_module):
    conn = MagicMock()
    event_id = "123"

    data = {
        "event_id": "123",
        "correlation_id": "c1",
        "tenant_id": "t1",
        "creation_timestamp": "2023-10-01T12:00:00Z",
        "last_updated_timestamp": "2023-10-01T12:01:00Z",
    }

    with patch.object(onestream_module, "push_records_to_kinesis") as mock_push, \
         patch.object(onestream_module, "CustomerReferralsFulfillmentActivityV1") as mock_schema_cls:

        fake_schema = MagicMock(name="schema_obj")
        mock_schema_cls.return_value = fake_schema

        # Make _build_onestream_payload deterministic without relying on Pydantic internals
        with patch.object(onestream_module, "_build_onestream_payload") as mock_build:
            mock_build.return_value = {"schemaName": "test_schema", "domainPayload": {"x": 1}}

            onestream_module.send_fulfillment_to_onestream(conn, event_id, data=data)

            mock_push.assert_called_once()
            args = mock_push.call_args.args
            assert args[1] == "arn:test"
            assert args[2] == [{"schemaName": "test_schema", "domainPayload": {"x": 1}}]


@patch.dict(os.environ, {"ONESTREAM_SCHEMA_NAME": "test_schema", "ONESTREAM_KINESIS_STREAM_ARN": "arn:test"})
def test_send_fulfillment_fetch_from_db_success(onestream_module):
    conn = MagicMock()
    event_id = "123"

    db_data = {
        "event_id": "123",
        "correlation_id": "c1",
        "tenant_id": "t1",
        "creation_timestamp": "2023-10-01T12:00:00Z",
        "last_updated_timestamp": "2023-10-01T12:01:00Z",
    }

    with patch.object(onestream_module, "get_fulfillment_event_for_onestream") as mock_get, \
         patch.object(onestream_module, "push_records_to_kinesis") as mock_push, \
         patch.object(onestream_module, "_build_onestream_payload") as mock_build, \
         patch.object(onestream_module, "CustomerReferralsFulfillmentActivityV1") as mock_schema_cls:

        mock_get.return_value = db_data
        mock_schema_cls.return_value = MagicMock(name="schema_obj")
        mock_build.return_value = {"schemaName": "test_schema", "domainPayload": {"y": 2}}

        onestream_module.send_fulfillment_to_onestream(conn, event_id)

        mock_get.assert_called_once_with(conn, event_id)
        mock_push.assert_called_once()


@patch.dict(os.environ, {"ONESTREAM_SCHEMA_NAME": "test_schema", "ONESTREAM_KINESIS_STREAM_ARN": "arn:test"})
def test_send_fulfillment_no_data_from_db_does_not_push(onestream_module):
    conn = MagicMock()
    event_id = "123"

    with patch.object(onestream_module, "get_fulfillment_event_for_onestream") as mock_get, \
         patch.object(onestream_module, "push_records_to_kinesis") as mock_push:
        mock_get.return_value = None

        onestream_module.send_fulfillment_to_onestream(conn, event_id)

        mock_push.assert_not_called()


@patch.dict(os.environ, {"ONESTREAM_SCHEMA_NAME": "test_schema", "ONESTREAM_KINESIS_STREAM_ARN": "arn:test"})
def test_send_fulfillment_schema_mapping_failure_does_not_push(onestream_module):
    conn = MagicMock()
    event_id = "123"
    data = {"event_id": "123"}

    with patch.object(onestream_module, "CustomerReferralsFulfillmentActivityV1") as mock_schema_cls, \
         patch.object(onestream_module, "push_records_to_kinesis") as mock_push:
        mock_schema_cls.side_effect = Exception("schema boom")

        onestream_module.send_fulfillment_to_onestream(conn, event_id, data=data)

        mock_push.assert_not_called()


@patch.dict(os.environ, {"ONESTREAM_SCHEMA_NAME": "test_schema", "ONESTREAM_KINESIS_STREAM_ARN": "arn:test"})
def test_send_fulfillment_push_failure_is_handled(onestream_module):
    conn = MagicMock()
    event_id = "123"
    data = {"event_id": "123"}

    with patch.object(onestream_module, "CustomerReferralsFulfillmentActivityV1") as mock_schema_cls, \
         patch.object(onestream_module, "_build_onestream_payload") as mock_build, \
         patch.object(onestream_module, "push_records_to_kinesis") as mock_push:

        mock_schema_cls.return_value = MagicMock(name="schema_obj")
        mock_build.return_value = {"schemaName": "test_schema", "domainPayload": {"z": 3}}
        mock_push.side_effect = Exception("kinesis boom")

        # Should not raise
        onestream_module.send_fulfillment_to_onestream(conn, event_id, data=data)

