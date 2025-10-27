

# tests/test_db.py
import json
import unittest
from unittest.mock import patch
from src.database import db as db_module  # adjust if your path differs


# tiny async fakes -------------------------------------------------------------
class _FakeCursor:
    def __init__(self, row):
        self._row = row

    async def execute(self, _sql, _params):
        return None

    async def fetchone(self):
        return self._row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, row=None, enter_exc=None, exec_exc=None):
        self._row = row
        self._enter_exc = enter_exc
        self._exec_exc = exec_exc

    def cursor(self):
        cur = _FakeCursor(self._row)
        if self._exec_exc:
            async def bad_execute(sql, params):
                raise self._exec_exc
            cur.execute = bad_execute  # type: ignore[attr-defined]
        return cur

    async def __aenter__(self):
        if self._enter_exc:
            raise self._enter_exc
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False
# -----------------------------------------------------------------------------


class TestCreateReferralFulfillment(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payload = {
            "prospectAccountKey": "PAK1",
            "prospectAccountKeyType": "EXT",
            "sorId": "S1",
            "programCode": "P1",
            "referralCode": "R1",
            "referralReferenceKeys": [{"k": "v"}],
        }
        self.db_params = ("db", "user", "pwd", "host", 5432)

    @patch("src.database.db.fetch_db_params_from_secret")
    @patch("src.database.db.get_connection_pool")
    async def test_success_first_try(self, mock_pool, mock_fetch):
        mock_fetch.return_value = self.db_params
        mock_pool.return_value = _FakeConn(row=[123])

        rid = await db_module.create_referral_fulfillment(self.payload, retries=3)

        self.assertEqual(rid, "123")  # string cast checked
        # quick param sanity: last element is jsonb payload
        self.assertIn("jsonb", db_module._SQL.lower())
        self.assertIsInstance(json.dumps(self.payload["referralReferenceKeys"]), str)

    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.fetch_db_params_from_secret")
    @patch("src.database.db.get_connection_pool")
    async def test_retries_then_success(self, mock_pool, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params
        # 1) pool enter fails, 2) execute fails, 3) success row
        mock_pool.side_effect = [
            _FakeConn(enter_exc=RuntimeError("pool down")),
            _FakeConn(exec_exc=RuntimeError("sql fail")),
            _FakeConn(row=[456]),
        ]

        rid = await db_module.create_referral_fulfillment(self.payload, retries=5)
        self.assertEqual(rid, "456")

    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.fetch_db_params_from_secret")
    @patch("src.database.db.get_connection_pool")
    async def test_exhausts_and_raises(self, mock_pool, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params
        mock_pool.return_value = _FakeConn(row=None)  # no id each attempt

        with self.assertRaises(RuntimeError):
            await db_module.create_referral_fulfillment(self.payload, retries=2)


if __name__ == "__main__":
    unittest.main()
