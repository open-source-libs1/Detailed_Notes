import unittest
from unittest.mock import MagicMock, patch, call

import app.main as main_mod


class TestRunAndMainCoverage(unittest.TestCase):
    def test_run_single_iteration_and_sleep(self):
        """
        Covers:
        - run(): while loop
        - query execute + fetchall + commit
        - iterating rows + calling process_fulfillment_record(dict(zip(...)))
        - sleep branch when interval < poll_interval
        """

        # Bypass __init__ to avoid constructing real clients
        p = main_mod.IncentiveProcessor.__new__(main_mod.IncentiveProcessor)

        # Set required attributes used by run()
        p.running = True
        p.poll_interval = 5  # ensures sleep branch executes

        # Mock DB objects used by run()
        p.referrals_db = MagicMock()
        p.referrals_db.cursor = MagicMock()
        p.referrals_db.connection = MagicMock()

        # run(): columns = [desc[0] for desc in cursor.description]
        p.referrals_db.cursor.description = [("col1",), ("col2",)]

        # run(): rows = cursor.fetchall()
        p.referrals_db.cursor.fetchall.return_value = [("v1", "v2")]

        # Stop loop after first processed row
        def _process_once(_row_dict):
            p.running = False

        p.process_fulfillment_record = MagicMock(side_effect=_process_once)

        # IMPORTANT:
        # Patch app.main.time (the module reference inside app.main),
        # so logging doesn't consume your side_effect values.
        with patch.object(main_mod, "time") as mock_time:
            mock_time.time.side_effect = [100.0, 101.0]  # start, stop
            mock_time.sleep = MagicMock()

            p.run()

        # Assertions
        p.referrals_db.cursor.execute.assert_called_once()
        p.referrals_db.cursor.fetchall.assert_called_once()
        p.referrals_db.connection.commit.assert_called_once()
        p.process_fulfillment_record.assert_called_once_with({"col1": "v1", "col2": "v2"})

        # interval = 1.0, poll_interval=5 => wait_time=4.0
        mock_time.sleep.assert_called_once_with(4.0)

    @patch.object(main_mod.signal, "signal")
    @patch.object(main_mod, "IncentiveProcessor")
    @patch.object(main_mod, "Secrets")
    def test_main_registers_signals_runs_and_closes_on_exception(
        self, mock_secrets_cls, mock_processor_cls, mock_signal_signal
    ):
        """
        Covers:
        - main(): Secrets() creation
        - main(): IncentiveProcessor(secrets) creation
        - main(): signal.signal(SIGINT/SIGTERM, handler)
        - main(): processor.run() called
        - main(): finally -> processor.referrals_db.close()
        """

        secrets = MagicMock()
        mock_secrets_cls.return_value = secrets

        processor = MagicMock()
        processor.run.side_effect = RuntimeError("boom")  # force finally path
        mock_processor_cls.return_value = processor

        with self.assertRaises(RuntimeError):
            main_mod.main()

        # Secrets() and IncentiveProcessor(secrets)
        mock_secrets_cls.assert_called_once()
        mock_processor_cls.assert_called_once_with(secrets)

        # Signal handlers registered
        mock_signal_signal.assert_has_calls(
            [
                call(main_mod.signal.SIGINT, processor.signal_handler),
                call(main_mod.signal.SIGTERM, processor.signal_handler),
            ],
            any_order=False,
        )

        # Finally block closes DB
        processor.referrals_db.close.assert_called_once()
