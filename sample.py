import unittest
from unittest.mock import patch
import runpy

from app.main import main


class TestMainFunction(unittest.TestCase):
    @patch("time.sleep", return_value=None)
    def test_main_with_iterations(self, mock_sleep):
        with patch("builtins.print") as mock_print:
            main(iterations=3)
            self.assertEqual(mock_print.call_count, 3)

    @patch("time.sleep", side_effect=Exception("Test Exception"))
    def test_main_with_exception(self, mock_sleep):
        with patch("builtins.print") as mock_print:
            main(iterations=2)
            self.assertIn(
                "Error occurred: Test Exception",
                [call[0][0] for call in mock_print.call_args_list],
            )

    def test_main_module_runs_main_guard(self):
        # Run app.main as if: python -m app.main
        # Make sleep raise SystemExit so it doesn't loop forever.
        with patch("time.sleep", side_effect=SystemExit), patch("builtins.print") as mock_print:
            with self.assertRaises(SystemExit):
                runpy.run_module("app.main", run_name="__main__")

            # Should have printed at least once before SystemExit
            mock_print.assert_any_call("This is the business rules task")


if __name__ == "__main__":
    unittest.main()
