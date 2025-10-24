import logging
from psycopg_pool import AsyncConnectionPool
from psycopg import OperationalError

logger = logging.getLogger(__name__)

_POOL: AsyncConnectionPool | None = None


def _conninfo(
    db_name: str,
    db_user: str,
    db_password: str,
    db_host: str,
    db_port: str,
) -> str:
    """Helper to format PostgreSQL connection string."""
    return (
        f"dbname={db_name} user={db_user} password={db_password} "
        f"host={db_host} port={db_port}"
    )


async def get_connection_pool(
    db_name: str,
    db_user: str,
    db_password: str,
    db_host: str,
    db_port: str,
    min_connections: int = 1,
    max_connections: int = 5,
) -> AsyncConnectionPool:
    """
    Initialize and return a global AsyncConnectionPool using psycopg3.
    """
    global _POOL  # type: ignore[attr-defined]

    if _POOL is None:
        if min_connections < 1:
            raise ValueError("min_connections must be >= 1")

        if min_connections >= max_connections:
            raise ValueError("min_connections must be less than max_connections")

        if max_connections > 10:
            raise ValueError("max_connections cannot exceed 10")

        try:
            _POOL = AsyncConnectionPool(
                conninfo=_conninfo(db_name, db_user, db_password, db_host, db_port),
                min_size=min_connections,
                max_size=max_connections,
                open=False,
            )
            await _POOL.open(wait=True)
            logger.info(
                "✅ DB async pool initialized (min=%s, max=%s) for host %s",
                min_connections,
                max_connections,
                db_host,
            )
        except OperationalError as e:
            logger.error("❌ Failed to initialize DB pool: %s", e)
            raise

    return _POOL


async def close_connection_pool() -> None:
    """Gracefully close the global async connection pool (if exists)."""
    global _POOL  # type: ignore[attr-defined]
    if _POOL:
        await _POOL.close()
        _POOL = None
        logger.info("✅ DB async pool closed.")





@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@


import unittest
from unittest.mock import patch, AsyncMock
from psycopg import OperationalError
from psycopg_pool import AsyncConnectionPool
from db_util import connection_pool


class TestConnectionPool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
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

        pool = await connection_pool.get_connection_pool(
            **self.db_args, min_connections=1, max_connections=5
        )

        self.assertEqual(pool, mock_instance)
        mock_pool.assert_called_once()
        mock_instance.open.assert_awaited_once()

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_reuse_existing_pool(self, mock_pool: AsyncMock) -> None:
        mock_instance = AsyncMock(spec=AsyncConnectionPool)
        connection_pool._POOL = mock_instance  # type: ignore[attr-defined]

        pool = await connection_pool.get_connection_pool(
            **self.db_args, min_connections=2, max_connections=6
        )

        mock_pool.assert_not_called()
        self.assertEqual(pool, mock_instance)

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_invalid_min_connections(self, mock_pool: AsyncMock) -> None:
        with self.assertRaises(ValueError):
            await connection_pool.get_connection_pool(
                **self.db_args, min_connections=0, max_connections=5
            )

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_invalid_min_greater_equal_max(self, mock_pool: AsyncMock) -> None:
        with self.assertRaises(ValueError):
            await connection_pool.get_connection_pool(
                **self.db_args, min_connections=5, max_connections=5
            )

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_invalid_max_connections_too_large(self, mock_pool: AsyncMock) -> None:
        with self.assertRaises(ValueError):
            await connection_pool.get_connection_pool(
                **self.db_args, min_connections=1, max_connections=11
            )

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_create_pool_failure(self, mock_pool: AsyncMock) -> None:
        mock_pool.side_effect = OperationalError("mock failure")

        with self.assertRaises(OperationalError):
            await connection_pool.get_connection_pool(
                **self.db_args, min_connections=1, max_connections=5
            )

    @patch("db_util.connection_pool.AsyncConnectionPool")
    async def test_close_pool(self, mock_pool: AsyncMock) -> None:
        mock_instance = AsyncMock(spec=AsyncConnectionPool)
        connection_pool._POOL = mock_instance  # type: ignore[attr-defined]

        await connection_pool.close_connection_pool()

        mock_instance.close.assert_awaited_once()
        self.assertIsNone(connection_pool._POOL)



