
class TestSignalAndCloseCoverage(unittest.TestCase):
    def test_signal_handler_sets_running_false_and_logs(self):
        # Bypass __init__ (no external clients)
        p = main_mod.IncentiveProcessor.__new__(main_mod.IncentiveProcessor)
        p.running = True

        with patch.object(main_mod, "logger") as mock_logger:
            p.signal_handler(signum=2, frame=None)

        self.assertFalse(p.running)
        mock_logger.info.assert_called_once()  # hits line 41

    def test_close_calls_referrals_db_close(self):
        # Bypass __init__
        p = main_mod.IncentiveProcessor.__new__(main_mod.IncentiveProcessor)
        p.referrals_db = MagicMock()

        p.close()

        p.referrals_db.close.assert_called_once()  # hits line 45

