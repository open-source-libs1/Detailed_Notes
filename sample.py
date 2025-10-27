# tests/test_db.py
import unittest
from unittest.mock import patch
from src.database import db as db_module  # adjust path if needed


class _FakeCursor:
    def __init__(self, behavior=None):
        self.behavior = behavior or {}

    async def execute(self, *_a, **_kw):
        # no recorder; just allow/raise if requested
        exc = self.behavior.get("execute_raises")
        if exc:
            raise exc

    async def fetchone(self):
        # default successful row if not provided
        return self.behavior.get("row", [1])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _FakeConn:
    def __init__(self, behavior=None):
        self.behavior = behavior or {}

    def cursor(self):
        return _FakeCursor(self.behavior)

    async def __aenter__(self):
        exc = self.behavior.get("enter_raises")
        if exc:
            raise exc
        return self

    async def __aexit__(self, *_):
        return False


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

        def _pool_factory(*_, **__):
            return _FakeConn({"row": [111]})

        with patch.object(db_module, "get_connection_pool", new=_pool_factory):
            rid = await db_module.create_referral_fulfillment(self.payload, retries=3)

        # returns referral_id as string
        self.assertEqual(rid, "111")

    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.fetch_db_params_from_secret")
    async def test_retry_then_success(self, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params

        attempts = iter([
            _FakeConn({"enter_raises": RuntimeError("pool not ready")}),
            _FakeConn({"execute_raises": RuntimeError("sql failed")}),
            _FakeConn({"row": [222]}),
        ])

        def _pool_factory(*_, **__):
            return next(attempts)

        with patch.object(db_module, "get_connection_pool", new=_pool_factory):
            rid = await db_module.create_referral_fulfillment(self.payload, retries=5)

        self.assertEqual(rid, "222")
        self.assertGreaterEqual(_sleep.call_count, 2)  # backoffs happened

    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.fetch_db_params_from_secret")
    async def test_exhaustion_raises(self, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params

        def _pool_factory(*_, **__):
            return _FakeConn({"row": None})

        with patch.object(db_module, "get_connection_pool", new=_pool_factory):
            with self.assertRaises(RuntimeError) as ctx:
                await db_module.create_referral_fulfillment(self.payload, retries=2)

        self.assertIn("DB returned no referral_id", str(ctx.exception))
        self.assertEqual(_sleep.call_count, 1)  # one backoff between attempts


if __name__ == "__main__":
    unittest.main()
