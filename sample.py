


# tests/test_db.py
import json
import unittest
from unittest.mock import patch
from src.database import db as db_module  # adjust if your package path differs


# --------- tiny async fakes (context-managers) ----------
class _FakeCursor:
    def __init__(self, behavior, rec):
        self.behavior = behavior or {}
        self.rec = rec

    async def execute(self, sql, params):
        self.rec["sql"] = sql
        self.rec["params"] = params
        if self.behavior.get("execute_raises"):
            raise self.behavior["execute_raises"]

    async def fetchone(self):
        return self.behavior.get("row", [1])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _FakeConn:
    def __init__(self, behavior=None, rec=None):
        self.behavior = behavior or {}
        self.rec = rec or {}

    def cursor(self):
        return _FakeCursor(self.behavior, self.rec)

    async def __aenter__(self):
        if self.behavior.get("enter_raises"):
            raise self.behavior["enter_raises"]
        return self

    async def __aexit__(self, *_):
        return False


# --------- tests ----------
class TestCreateReferralFulfillment(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payload = {
            "prospectAccountKey": "PAK",
            "prospectAccountKeyType": "EXT",
            "sorId": "S1",
            "programCode": "PG",
            "referralCode": "RC",
            "referralReferenceKeys": [{"k": "v"}],
        }
        self.db_params = ("db", "user", "pwd", "host", 5432)

    @patch("src.database.db.fetch_db_params_from_secret")
    async def test_success_first_try(self, mock_fetch):
        mock_fetch.return_value = self.db_params
        rec = {}

        # IMPORTANT: plain callable returning an async context-manager object
        def _pool_factory(*_, **__):
            return _FakeConn({"row": [111]}, rec)

        with patch.object(db_module, "get_connection_pool", new=_pool_factory):
            rid = await db_module.create_referral_fulfillment(self.payload, retries=3)

        self.assertEqual(rid, "111")
        self.assertEqual(rec["sql"], db_module._SQL)
        self.assertEqual(
            rec["params"],
            [
                "PAK",
                "EXT",
                "S1",
                "PG",
                "RC",
                json.dumps([{"k": "v"}]),
            ],
        )

    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.fetch_db_params_from_secret")
    async def test_retry_then_success(self, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params
        rec3 = {}
        attempts = iter([
            _FakeConn({"enter_raises": RuntimeError("pool not ready")}, {}),
            _FakeConn({"execute_raises": RuntimeError("sql boom")}, {}),
            _FakeConn({"row": [222]}, rec3),
        ])

        def _pool_factory(*_, **__):
            return next(attempts)

        with patch.object(db_module, "get_connection_pool", new=_pool_factory):
            rid = await db_module.create_referral_fulfillment(self.payload, retries=5)

        self.assertEqual(rid, "222")
        self.assertEqual(rec3["sql"], db_module._SQL)
        self.assertGreaterEqual(_sleep.call_count, 2)

    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.fetch_db_params_from_secret")
    async def test_exhaustion_raises_last_error(self, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params

        def _pool_factory(*_, **__):
            return _FakeConn({"row": None}, {})  # fetchone() => None every time

        with patch.object(db_module, "get_connection_pool", new=_pool_factory):
            with self.assertRaises(RuntimeError) as ctx:
                await db_module.create_referral_fulfillment(self.payload, retries=2)

        self.assertIn("DB returned no referral_id", str(ctx.exception))
        self.assertEqual(_sleep.call_count, 1)  # one backoff between two attempts


if __name__ == "__main__":
    unittest.main()






###############################


# src/utils/database_utils.py
from __future__ import annotations
import os
import boto3
import ast
from aws_util import retrieve_secret_value

def fetch_db_params_from_secret():
    """
    Fetches credentials stored in AWS Secrets Manager.
    """
    secrets_manager = boto3.client("secretsmanager")
    secret_name = os.environ["DB_SECRET_ARN"]
    raw = retrieve_secret_value(secrets_manager, secret_name)

    # Handle empty/invalid payloads from Secrets Manager
    try:
        secret = ast.literal_eval(raw) if raw else None
    except (ValueError, SyntaxError):
        secret = None

    if not secret:
        raise ValueError(f"Failed to retrieve secret for {secret_name}")

    return (
        secret["dbname"],
        secret["username"],
        secret["password"],
        secret["host"],
        secret["port"],
    )






