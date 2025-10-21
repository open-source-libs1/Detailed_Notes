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
            # Accept both a named 'kwargs' and any other **extra keyword args
            def __init__(self, *, conninfo=None, min_size=None, max_size=None,
                         kwargs=None, **extra):
                created["conninfo"] = conninfo
                created["min"] = min_size
                created["max"] = max_size
                created["kwargs"] = kwargs or {}
                created["extra"] = extra or {}

            def connection(self):
                return DummyConnCtx()

        with patch("src.database.db.AsyncConnectionPool",
                   side_effect=lambda *a, **k: DummyPool(**k)):
            cm = create_connection()  # returns async context manager
            async with cm as conn:
                self.assertEqual(conn, "CONN")

        # Assert pool sizes picked up from env and conninfo built
        self.assertIn("dbname=n", created["conninfo"])
        self.assertEqual(created["min"], 2)
        self.assertEqual(created["max"], 4)

        # Accept either style: passed via named 'kwargs' or via **extra
        combined = {**(created.get("kwargs") or {}), **(created.get("extra") or {})}
        self.assertIn("application_name", combined)
        # options should also be present if your db.py sets them
        # (won't fail if your implementation omits options)
        if "options" in combined:
            self.assertIn("statement_timeout", combined["options"])
