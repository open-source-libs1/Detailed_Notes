import unittest
from unittest.mock import MagicMock, patch, call

import app.main as main_mod


class TestRunAndMainCoverage(unittest.TestCase):
    def test_run_single_iteration_and_sleep(self):
        p = main_mod.IncentiveProcessor.__new__(main_mod.IncentiveProcessor)  # bypass __init__
        p.running = True
        p.poll_interval = 5  # force sleep branch

        # Mock DB shape used by run()
        p.referrals_db = MagicMock()
        p.referrals_db.cursor = MagicMock()
        p.referrals_db.cursor.description = [("col1",), ("col2",)]
        p.referrals_db.cursor.fetchall.return_value = [("v1", "v2")]

        # Stop loop after first row processed
        def _process_once(_row_dict):
            p.running = False

        p.process_fulfillment_record = MagicMock(side_effect=_process_once)

        with patch.object(main_mod.time, "time", side_effect=[100.0, 101.0]), \
             patch.object(main_mod.time, "sleep") as mock_sleep:
            p.run()

        # Assertions: query executed, commit called, row processed, sleep called with remaining time
        p.referrals_db.cursor.execute.assert_called_once()  # covers execute path
        p.referrals_db.connection.commit.assert_called_once()  # covers commit path
        p.process_fulfillment_record.assert_called_once_with({"col1": "v1", "col2": "v2"})
        mock_sleep.assert_called_once_with(4.0)  # 5 - (101-100)

    @patch.object(main_mod.signal, "signal")
    @patch.object(main_mod, "IncentiveProcessor")
    @patch.object(main_mod, "Secrets")
    def test_main_registers_signals_runs_and_closes_on_exception(
        self, mock_secrets_cls, mock_processor_cls, mock_signal_signal
    ):
        secrets = MagicMock()
        mock_secrets_cls.return_value = secrets

        processor = MagicMock()
        processor.run.side_effect = RuntimeError("boom")  # force finally path
        mock_processor_cls.return_value = processor

        with self.assertRaises(RuntimeError):
            main_mod.main()

        # main(): Secrets() -> IncentiveProcessor(secrets)
        mock_secrets_cls.assert_called_once()
        mock_processor_cls.assert_called_once_with(secrets)

        # main(): registers SIGINT + SIGTERM handlers
        mock_signal_signal.assert_has_calls(
            [
                call(main_mod.signal.SIGINT, processor.signal_handler),
                call(main_mod.signal.SIGTERM, processor.signal_handler),
            ],
            any_order=False,
        )

        # main(): finally closes DB
        processor.referrals_db.close.assert_called_once()
