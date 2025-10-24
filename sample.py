import unittest
from unittest.mock import patch, AsyncMock
from psycopg import OperationalError
from psycopg_pool import AsyncConnectionPool
from db_util.connection_pool import get_connection_pool, close_connection_pool


class TestConnectionPool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from db_util import connection_pool
        connection_pool._POOL = None  # type: ignore[attr-defined]
        self.db_args: dict[str, str] = {
            "db_name": "test_db",
            "db_user": "test_user",
            "db_password": "test_pass",
            "db_host": "localhost",
            "db_port": "5432",
        }

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_create_pool_success(self, mock_pool: AsyncMock) -> None:
        mock_instance = AsyncMock(spec=AsyncConnectionPool)
        mock_pool.return_value = mock_instance

        pool = await get_connection_pool(**self.db_args, min_connections=1, max_connections=5)

        mock_pool.assert_called_once()
        mock_instance.open.assert_awaited_once()
        self.assertEqual(pool, mock_instance)

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_reuse_existing_pool(self, mock_pool: AsyncMock) -> None:
        from db_util import connection_pool
        mock_instance = AsyncMock(spec=AsyncConnectionPool)
        connection_pool._POOL = mock_instance  # type: ignore[attr-defined]

        pool = await get_connection_pool(**self.db_args, min_connections=2, max_connections=6)

        mock_pool.assert_not_called()
        self.assertIs(pool, mock_instance)

    async def test_invalid_min_connections(self) -> None:
        with self.assertRaises(ValueError):
            await get_connection_pool(**self.db_args, min_connections=0, max_connections=5)

    async def test_invalid_min_greater_equal_max(self) -> None:
        with self.assertRaises(ValueError):
            await get_connection_pool(**self.db_args, min_connections=5, max_connections=5)

    async def test_invalid_max_connections_too_large(self) -> None:
        with self.assertRaises(ValueError):
            await get_connection_pool(**self.db_args, min_connections=1, max_connections=11)

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_create_pool_failure(self, mock_pool: AsyncMock) -> None:
        mock_pool.side_effect = OperationalError("mock failure")
        with self.assertRaises(OperationalError):
            await get_connection_pool(**self.db_args, min_connections=1, max_connections=5)

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_close_pool(self, mock_pool: AsyncMock) -> None:
        from db_util import connection_pool
        mock_instance = AsyncMock(spec=AsyncConnectionPool)
        connection_pool._POOL = mock_instance  # type: ignore[attr-defined]

        await close_connection_pool()

        mock_instance.close.assert_awaited_once()
        self.assertIsNone(connection_pool._POOL)
