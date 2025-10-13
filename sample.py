






# src/db.py
# Single, slightly battle-hardened helper that runs a fixed INSERT into epic.
# Assumes you already provide pool.get_pool() returning a psycopg2-like pool.

from __future__ import annotations
import logging
import time
from typing import Optional
from pool import get_pool  # provided by you

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

_SQL = 'INSERT INTO epic("network_name","security_key","security_mode") VALUES (%s,%s,%s);'

def insert_epic(network_name: str, security_key: str, security_mode: str, retries: int = 5) -> int:
    """
    Insert one row into epic using the fixed SQL above.
    Params are bound in the order: network_name, security_key, security_mode.
    Returns 1 on success. Retries up to `retries` times for any error or wrong rowcount.
    """
    pool = get_pool()
    last_err: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        conn = pool.getconn()
        try:
            log.info(
                "epic-insert attempt=%s network_name=%r security_key=%r security_mode=%r",
                attempt, network_name, security_key, security_mode
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_SQL, [network_name, security_key, security_mode])
                    rows = cur.rowcount
                    if rows == 1:
                        log.info("epic-insert success attempt=%s", attempt)
                        return 1
                    last_err = AssertionError(f"expected 1 row, got {rows}")
                    log.warning("epic-insert unexpected-rowcount attempt=%s rowcount=%s", attempt, rows)
        except Exception as e:
            last_err = e
            log.warning("epic-insert error attempt=%s err=%r", attempt, e)
        finally:
            try:
                pool.putconn(conn)
            except Exception as e2:
                log.error("putconn failed err=%r", e2)

        # light exponential backoff (capped) before next try
        if attempt < retries:
            try:
                time.sleep(min(0.2 * (2 ** (attempt - 1)), 1.0))
            except Exception:  # sleep should never fail, but don't block retry loop
                pass

    # exhausted
    if last_err:
        log.error("epic-insert exhausted retries=%s last_err=%r", retries, last_err)
        raise last_err
    raise RuntimeError("epic-insert failed for unknown reason")





########################################





# src/handler.py
# FastAPI endpoint + Mangum adapter for Lambda.

from typing import Any, Dict
import logging
from fastapi import FastAPI, HTTPException, Request
from .db import insert_epic

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

app = FastAPI()

_REQ_FIELDS = ["network_name", "security_key", "security_mode"]

def _require(body: Dict[str, Any]) -> Dict[str, Any]:
    missing = [k for k in _REQ_FIELDS if k not in body]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing fields: {', '.join(missing)}")
    return {k: body[k] for k in _REQ_FIELDS}

@app.post("/insert")
async def insert_endpoint(request: Request) -> Dict[str, Any]:
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    data = _require(body)

    try:
        n = insert_epic(data["network_name"], data["security_key"], data["security_mode"])
        return {"inserted": n}
    except HTTPException:
        raise
    except Exception:
        log.exception("insert failed")
        raise HTTPException(status_code=500, detail="Insert failed")

# Lambda adapter (if you deploy via API Gateway HTTP API)
try:
    from mangum import Mangum  # type: ignore
    handler = Mangum(app)
except Exception:
    handler = None



##########################################



import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import src.db as db
import src.handler as handler

GOOD = {"network_name": "netA", "security_key": "sk1", "security_mode": "modeX"}

def make_pool():
    pool = MagicMock(name="pool")
    conn = MagicMock(name="conn")
    cur = MagicMock(name="cursor")

    # context manager behavior
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    cm = MagicMock(name="cursor_cm")
    cm.__enter__.return_value = cur
    cm.__exit__.return_value = False
    conn.cursor.return_value = cm

    pool.getconn.return_value = conn
    return pool, conn, cur

class TestDB(unittest.TestCase):
    @patch("src.db.get_pool")
    @patch("src.db.time.sleep", return_value=None)
    def test_success_first_try(self, _sleep, get_pool_mock):
        pool, conn, cur = make_pool()
        cur.rowcount = 1
        get_pool_mock.return_value = pool

        out = db.insert_epic("N", "K", "M")
        self.assertEqual(out, 1)
        cur.execute.assert_called_once_with(
            'INSERT INTO epic("network_name","security_key","security_mode") VALUES (%s,%s,%s);',
            ["N", "K", "M"],
        )
        pool.putconn.assert_called_with(conn)

    @patch("src.db.get_pool")
    @patch("src.db.time.sleep", return_value=None)
    def test_exception_then_success(self, _sleep, get_pool_mock):
        pool, conn, cur = make_pool()
        get_pool_mock.return_value = pool

        def side_effect(*_a, **_k):
            if side_effect.calls < 1:
                side_effect.calls += 1
                raise RuntimeError("db blip")
            cur.rowcount = 1
        side_effect.calls = 0
        cur.execute.side_effect = side_effect

        out = db.insert_epic("N2", "K2", "M2")
        self.assertEqual(out, 1)
        self.assertEqual(pool.putconn.call_count, 2)

    @patch("src.db.get_pool")
    @patch("src.db.time.sleep", return_value=None)
    def test_zero_rowcount_retries_then_fail(self, _sleep, get_pool_mock):
        pool, _, cur = make_pool()
        get_pool_mock.return_value = pool
        def zero(*_a, **_k):
            cur.rowcount = 0
        cur.execute.side_effect = zero

        with self.assertRaises(AssertionError):
            db.insert_epic("N3", "K3", "M3", retries=4)
        self.assertEqual(pool.putconn.call_count, 4)

    @patch("src.db.get_pool")
    @patch("src.db.time.sleep", return_value=None)
    def test_all_attempts_raise(self, _sleep, get_pool_mock):
        pool, _, cur = make_pool()
        get_pool_mock.return_value = pool
        cur.execute.side_effect = RuntimeError("hard fail")

        with self.assertRaises(RuntimeError):
            db.insert_epic("N4", "K4", "M4", retries=5)
        self.assertEqual(pool.putconn.call_count, 5)

class TestHandler(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(handler.app)

    @patch("src.handler.insert_epic", return_value=1)
    def test_endpoint_ok(self, ins):
        r = self.client.post("/insert", json=GOOD)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"inserted": 1})
        ins.assert_called_once_with("netA", "sk1", "modeX")

    def test_endpoint_missing_field(self):
        bad = dict(GOOD); bad.pop("security_mode")
        r = self.client.post("/insert", json=bad)
        self.assertEqual(r.status_code, 400)
        self.assertIn("missing fields", r.text)

    def test_endpoint_bad_json(self):
        r = self.client.post("/insert", data="{notjson")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Invalid JSON", r.text)

    @patch("src.handler.insert_epic", side_effect=RuntimeError("db down"))
    def test_endpoint_db_fail(self, _ins):
        r = self.client.post("/insert", json=GOOD)
        self.assertEqual(r.status_code, 500)
        self.assertIn("Insert failed", r.text)

if __name__ == "__main__":
    unittest.main()
