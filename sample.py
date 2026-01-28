from collections import deque
from contextlib import contextmanager

@contextmanager
def _noop_lock():
    yield

from unittest.mock import ANY  # optional, only if you want flexible assertions


class TestMoneyMovementClient(unittest.TestCase):
    # keep your existing setUp + existing tests unchanged

    @patch("app.services.money_movement.requests.post")
    def test_make_post_request_cleans_old_timestamps(self, mock_post):
        """
        Covers the first cleanup loop:
        while self._request_times and now - self._request_times[0] > 1:
            popleft()
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.text = '{"result":"success"}'
        mock_post.return_value = mock_response

        data = MagicMock()
        data.moneyFlowRequestId = "reqid"
        data.model_dump.return_value = {"some": "data"}

        # Make TPS limit small and isolate request_times per test
        with patch("app.services.money_movement.Constants.MMAPI_TPS_LIMIT", 2):
            self.client._request_times = deque([0.0, 0.5], maxlen=2)  # both should be >1s old
            self.client._lock = _noop_lock()  # avoid real threading lock behavior

            with patch("app.services.money_movement.time.time", return_value=2.0):
                self.client.make_post_request("customer", data)

            # After cleanup both removed, then "now" appended => only one entry remains
            self.assertEqual(list(self.client._request_times), [2.0])

    @patch("app.services.money_movement.requests.post")
    def test_make_post_request_hits_tps_limit_sleeps_and_recleans(self, mock_post):
        """
        Covers TPS limit block:
        if len(self._request_times) >= Constants.MMAPI_TPS_LIMIT:
            logger.info(...)
            sleep_time = ...
            time.sleep(...)
            now = time.time()
            while ...: popleft()
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.text = '{"result":"success"}'
        mock_post.return_value = mock_response

        data = MagicMock()
        data.moneyFlowRequestId = "reqid"
        data.model_dump.return_value = {"some": "data"}

        with patch("app.services.money_movement.Constants.MMAPI_TPS_LIMIT", 2):
            # Pre-fill to the TPS limit so the throttle branch triggers
            self.client._request_times = deque([0.0, 0.2], maxlen=2)
            self.client._lock = _noop_lock()

            with patch("app.services.money_movement.logger") as mock_logger, \
                 patch("app.services.money_movement.time.sleep") as mock_sleep, \
                 patch("app.services.money_movement.time.time", side_effect=[0.3, 1.05]):

                # now=0.3 -> len==2 triggers throttle
                # sleep_time = 1 - (0.3 - 0.0) = 0.7
                self.client.make_post_request("customer", data)

                mock_logger.info.assert_any_call(
                    "Money Movement TPS limit reached: 2, waiting..."
                )
                mock_sleep.assert_called_once_with(0.7)

            # After second now=1.05, old 0.0 gets popped in the second cleanup,
            # and 1.05 appended
            self.assertEqual(list(self.client._request_times), [0.2, 1.05])

