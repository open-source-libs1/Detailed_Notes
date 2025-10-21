import json
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

# Make sure the parent directory (that CONTAINS 'src') is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # -> lambda/
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.main import app, create_referral, health, not_found, _get_json_body  # type: ignore


class FakeEvent:
    def __init__(self, body: dict | None, headers=None):
        self.headers = headers or {"host": "api.example.com", "x-forwarded-proto": "https"}
        self._body = body

    @property
    def json_body(self):
        if self._body is None:
            raise ValueError("bad json")
        return self._body


class TestHandler(unittest.IsolatedAsyncioTestCase):
    def set_event(self, body, headers=None):
        app._current_event = FakeEvent(body, headers=headers)  # type: ignore

    @patch("src.main.create_referral_fulfillment", new_callable=AsyncMock, return_value="123")
    async def test_201(self, _db):
        body = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S",
            "referralReferenceKeys": [],
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }
        self.set_event(body)
        res = await create_referral()
        self.assertEqual(res["statusCode"], 201)
        payload = json.loads(res["body"])
        self.assertEqual(payload["referralId"], "123")
        self.assertIn("/enterprise/referrals/123", res["headers"]["Location"])

    async def test_400_missing_body(self):
        app._current_event = FakeEvent(None)  # type: ignore
        res = await create_referral()
        self.assertEqual(res["statusCode"], 400)

    async def test_400_validation(self):
        # intentionally invalid/missing
        self.set_event({"programCode": "BAD SPACE"})
        res = await create_referral()
        self.assertEqual(res["statusCode"], 400)

    @patch("src.main.create_referral_fulfillment", new_callable=AsyncMock, side_effect=RuntimeError("db down"))
    async def test_500_db(self, _db):
        body = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S",
            "referralReferenceKeys": [],
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }
        self.set_event(body)
        res = await create_referral()
        self.assertEqual(res["statusCode"], 500)

    @patch("src.main.create_referral_fulfillment", new_callable=AsyncMock, return_value="123")
    async def test_201_no_host_header(self, _db):
        # Cover the branch where host header is missing -> relative Location
        body = {
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S",
            "referralReferenceKeys": [],
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
        }
        self.set_event(body, headers={})  # no host/proto
        res = await create_referral()
        self.assertEqual(res["statusCode"], 201)
        self.assertTrue(res["headers"]["Location"].startswith("/enterprise/referrals/"))

    def test_get_json_body_callable_and_errors(self):
        # Cover _get_json_body() callable form and error paths

        class CallableEvent:
            def __init__(self, body):
                self.headers = {}
                self._body = body

            def json_body(self):  # callable
                return self._body

        # callable success
        app._current_event = CallableEvent({"x": 1})  # type: ignore
        got = _get_json_body()
        self.assertEqual(got, {"x": 1})

        # error: no event
        app._current_event = None  # type: ignore
        with self.assertRaises(Exception):
            _get_json_body()


# ---- simple sync tests for the sync helpers (no patches needed) --------------

def test_health_direct():
    res = health()
    assert res["statusCode"] == 200


def test_not_found_direct():
    res = not_found({})
    assert res["statusCode"] == 404



###############################



import os
import unittest
from unittest.mock import patch, AsyncMock, MagicMock, call

from src.database.db import create_referral_fulfillment, create_connection
import src.database.db as dbmod


@patch.dict(os.environ, {
    "DB_USERNAME": "u",
    "DB_PASSWORD": "p",
    "DB_NAME": "n",
    "DB_HOST": "h",
    "DB_PORT": "5432",
    "DB_POOL_MIN": "2",
    "DB_POOL_MAX": "4",
}, clear=True)
class TestDBPoolInit(unittest.IsolatedAsyncioTestCase):
    async def test_pool_init_and_connection_ctx(self):
        # Reset module-level pool to cover init path
        dbmod._POOL = None

        created = {}

        class DummyConnCtx:
            async def __aenter__(self): return "CONN"
            async def __aexit__(self, exc_type, exc, tb): return False

        class DummyPool:
            def __init__(self, *, conninfo=None, min_size=None, max_size=None, kwargs=None, **_):
                created["conninfo"] = conninfo
                created["min"] = min_size
                created["max"] = max_size
                created["kwargs"] = kwargs

            def connection(self):
                return DummyConnCtx()

        with patch("src.database.db.AsyncConnectionPool", side_effect=lambda *a, **k: DummyPool(**k)):
            cm = create_connection()  # returns async context manager
            async with cm as conn:
                self.assertEqual(conn, "CONN")

        # Assert pool sizes picked up from env and conninfo built
        self.assertIn("dbname=n", created["conninfo"])
        self.assertEqual(created["min"], 2)
        self.assertEqual(created["max"], 4)
        self.assertIn("application_name", created["kwargs"] or {})


@patch.dict(os.environ, {
    "DB_USERNAME": "u",
    "DB_PASSWORD": "p",
    "DB_NAME": "n",
    "DB_HOST": "h",
    "DB_PORT": "5432",
}, clear=True)
class TestDBBackoff(unittest.IsolatedAsyncioTestCase):
    @patch("src.database.db.time.sleep", return_value=None)
    @patch("src.database.db.create_connection")
    async def test_backoff_calls(self, create_conn_mock, _sleep):
        # Fail first two attempts, succeed on third; assert backoff timings
        conn = MagicMock(name="conn")
        cur = MagicMock(name="cursor")

        async def aenter_cur(): return cur
        async def aexit_cur(_t, _e, _tb): return False

        curctx = type("CurCtx", (), {"__aenter__": staticmethod(aenter_cur), "__aexit__": staticmethod(aexit_cur)})()
        conn.cursor.return_value = curctx

        async def aenter_conn(): return conn
        async def aexit_conn(_t, _e, _tb): return False
        create_conn_mock.return_value = type("ConnCtx", (), {"__aenter__": staticmethod(aenter_conn), "__aexit__": staticmethod(aexit_conn)})()

        calls = {"n": 0}

        async def exec_side_effect(*_a, **_k):
            # raise on first two attempts
            if calls["n"] < 2:
                calls["n"] += 1
                raise RuntimeError("blip")
            return None

        row_vals = iter([["RID-3"]])
        cur.execute = AsyncMock(side_effect=exec_side_effect)
        cur.fetchone = AsyncMock(side_effect=lambda: next(row_vals))

        rid = await create_referral_fulfillment({
            "prospectAccountKey": "123",
            "prospectAccountKeyType": "CARD_ACCOUNT_ID",
            "sorId": "S",
            "programCode": "PROGRAM_001",
            "referralCode": "REFERRAL_ABC",
            "referralReferenceKeys": [],
        }, retries=3)

        self.assertEqual(rid, "RID-3")
        # Verify backoff calls: 0.2 (after attempt 1), 0.4 (after attempt 2)
        self.assertEqual(_sleep.call_args_list, [call(0.2), call(0.4)])
