import unittest
from unittest.mock import patch, MagicMock
import os
import ast
from src.utils import database_utils


class TestFetchDBParamsFromSecret(unittest.TestCase):
    """Unit tests for fetch_db_params_from_secret()"""

    @patch.dict(os.environ, {"DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"})
    @patch("src.utils.database_utils.retrieve_secret_value")
    @patch("src.utils.database_utils.boto3.client")
    def test_fetch_db_params_success(self, mock_boto_client, mock_retrieve_secret_value):
        """✅ Should return DB params tuple when secret retrieval succeeds"""
        mock_boto_client.return_value = MagicMock()
        fake_secret = {
            "dbname": "test_db",
            "username": "admin",
            "password": "pass123",
            "host": "localhost",
            "port": "5432"
        }
        mock_retrieve_secret_value.return_value = str(fake_secret)

        result = database_utils.fetch_db_params_from_secret()

        expected = (
            fake_secret["dbname"],
            fake_secret["username"],
            fake_secret["password"],
            fake_secret["host"],
            fake_secret["port"],
        )
        self.assertEqual(result, expected)
        mock_boto_client.assert_called_once_with("secretsmanager")
        mock_retrieve_secret_value.assert_called_once()

    @patch.dict(os.environ, {"DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"})
    @patch("src.utils.database_utils.retrieve_secret_value", return_value="")
    @patch("src.utils.database_utils.boto3.client")
    def test_fetch_db_params_failure_empty_secret(self, mock_boto_client, mock_retrieve_secret_value):
        """❌ Should raise ValueError when secret retrieval fails"""
        mock_boto_client.return_value = MagicMock()

        with self.assertRaises(ValueError) as ctx:
            database_utils.fetch_db_params_from_secret()
        self.assertIn("Failed to retrieve secret", str(ctx.exception))

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_variable(self):
        """❌ Should raise KeyError when DB_SECRET_ARN is missing"""
        with self.assertRaises(KeyError):
            database_utils.fetch_db_params_from_secret()


if __name__ == "__main__":
    unittest.main()
