# tests/test_db.py
import json
import unittest
from unittest.mock import patch

# Import the module under test
from src.database import db as db_module  # adjust if your path differs


# ----- Simple async-aware fakes for the connection + cursor -----
class _FakeCursor:
    def __init__(self, behavior: dict, recorder: dict):
        self._behavior = behavior or {}
        self._recorder = recorder

    async def execute(self, sql, params):
        # record what was executed for assertions
        self._recorder["sql"] = sql
        self._recorder["params"] = params
        exc = self._behavior.get("execute_raises")
        if exc:
            raise exc  # simulate SQL error

    async def fetchone(self):
        return self._behavior.get("row", [1])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    """Acts as the object returned by get_connection_pool(...)."""

    def __init__(self, behavior: dict, recorder: dict):
        self._behavior = behavior or {}
        self._recorder = recorder
        self.last_cursor = None

    def cursor(self):
        self.last_cursor = _FakeCursor(self._behavior, self._recorder)
        return self.last_cursor

    async def __aenter__(self):
        exc = self._behavior.get("enter_raises")
        if exc:
            raise exc  # simulate pool/connection acquisition failure
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestCreateReferralFulfillment(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Minimal valid payload
        self.payload = {
            "prospectAccountKey": "PAK-1",
            "prospectAccountKeyType": "EXT",
            "sorId": "S1",
            "programCode": "PGR",
            "referralCode": "REF-42",
            "referralReferenceKeys": [{"k": "v"}],
        }

        # Common DB params returned by the secret helper
        self.db_params = ("db", "user", "pwd", "host", 5432)

    # ---------- Happy path: success on first try ----------
    @patch("src.database.db.fetch_db_params_from_secret")
    @patch("src.database.db.get_connection_pool")
    async def test_success_first_attempt(self, mock_pool, mock_fetch):
        mock_fetch.return_value = self.db_params

        rec = {}
        mock_pool.return_value = _FakeConn({"row": [111]}, rec)

        with self.assertLogs(db_module.logger, level="INFO") as logs:
            rid = await db_module.create_referral_fulfillment(self.payload, retries=3)

        self.assertEqual(rid, "111")
        # verify SQL + params were passed to cursor.execute
        self.assertEqual(rec["sql"], db_module._SQL)
        self.assertEqual(
            rec["params"],
            [
                self.payload["prospectAccountKey"],
                self.payload["prospectAccountKeyType"],
                self.payload["sorId"],
                self.payload["programCode"],
                self.payload["referralCode"],
                json.dumps(self.payload["referralReferenceKeys"]),
            ],
        )
        # verify log contains success on attempt 1
        self.assertTrue(any("db-insert success attempt=1" in line for line in logs.output))
        mock_fetch.assert_called_once()

    # ---------- Success after transient failures (retries) ----------
    @patch("src.database.db.time.sleep", return_value=None)  # avoid real sleeping
    @patch("src.database.db.fetch_db_params_from_secret")
    @patch("src.database.db.get_connection_pool")
    async def test_success_after_retries(self, mock_pool, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params

        # 1st: pool enter fails; 2nd: cursor.execute fails; 3rd: success
        rec3 = {}
        mock_pool.side_effect = [
            _FakeConn({"enter_raises": RuntimeError("pool down")}, {}),
            _FakeConn({"execute_raises": RuntimeError("sql fail")}, {}),
            _FakeConn({"row": [222]}, rec3),
        ]

        with self.assertLogs(db_module.logger, level="WARNING") as warn_logs:
            rid = await db_module.create_referral_fulfillment(self.payload, retries=5)

        self.assertEqual(rid, "222")
        # There should be at least two warnings (two failed attempts)
        self.assertGreaterEqual(len(warn_logs.output), 2)
        # sleep should have been invoked for backoff twice
        self.assertGreaterEqual(_sleep.call_count, 2)
        # final success recorded expected SQL
        self.assertEqual(rec3["sql"], db_module._SQL)

    # ---------- Exhaustion: raises after all retries ----------
    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.fetch_db_params_from_secret")
    @patch("src.database.db.get_connection_pool")
    async def test_exhausts_retries_and_raises(self, mock_pool, mock_fetch, _sleep):
        mock_fetch.return_value = self.db_params
        # fetchone returns None -> module raises RuntimeError each attempt
        mock_pool.return_value = _FakeConn({"row": None}, {})

        with self.assertLogs(db_module.logger, level="ERROR") as err_logs:
            with self.assertRaises(RuntimeError) as ctx:
                await db_module.create_referral_fulfillment(self.payload, retries=2)

        self.assertIn("DB returned no referral_id", str(ctx.exception))
        self.assertTrue(any("db-insert exhausted retries" in l for l in err_logs.output))
        self.assertEqual(_sleep.call_count, 1)  # one backoff between two attempts

    # ---------- Ensures non-string IDs are converted to string ----------
    @patch("src.database.db.fetch_db_params_from_secret")
    @patch("src.database.db.get_connection_pool")
    async def test_numeric_id_is_cast_to_string(self, mock_pool, mock_fetch):
        mock_fetch.return_value = self.db_params
        mock_pool.return_value = _FakeConn({"row": [9876]}, {})

        rid = await db_module.create_referral_fulfillment(self.payload, retries=1)
        self.assertIsInstance(rid, str)
        self.assertEqual(rid, "9876")


if __name__ == "__main__":
    unittest.main()
