from contextlib import contextmanager

@contextmanager
def _noop_context(*args, **kwargs):
    yield


class TestIncentiveProcessor(unittest.TestCase):
    ...
    # keep your existing setUp + tests unchanged

    @patch('app.main.init_validate_context')
    @patch('app.main.create_money_movement_request')
    @patch('app.main.extract_json_body')
    def test_process_payment_no_escid_calls_update_retry(
        self, mock_extract_json, mock_create_request, mock_init_validate
    ):
        # Make context manager no-op
        mock_init_validate.return_value = _noop_context()
        mock_create_request.return_value = MagicMock()

        data = {
            'customer_account_key': '123',
            'customer_retry_count': 0,
            'event_id': 'EVT-1',
            'referral_code': 'RC-1',
        }

        # Force: no ESCID
        self.processor.tcr_client.get_account_escid.return_value = None

        # Spy / stub retry + status functions
        self.processor.update_retry = MagicMock()
        self.processor.update_customer_status = MagicMock()

        self.processor.process_payment(data, 'customer', 100)

        self.processor.update_retry.assert_called_once_with(data, 'customer')
        self.processor.update_customer_status.assert_not_called()
        self.processor.money_movement_client.make_post_request.assert_not_called()

    @patch('app.main.init_validate_context')
    @patch('app.main.create_money_movement_request')
    @patch('app.main.extract_json_body')
    def test_process_payment_duplicate_409_mmpc009_updates_status_ff(
        self, mock_extract_json, mock_create_request, mock_init_validate
    ):
        mock_init_validate.return_value = _noop_context()
        mock_create_request.return_value = MagicMock()
        mock_extract_json.return_value = {}  # not used in 409/MMPC009 branch

        data = {
            'customer_account_key': '123',
            'customer_retry_count': 0,
            'event_id': 'EVT-2',
            'referral_code': 'RC-2',
        }

        self.processor.tcr_client.get_account_escid.return_value = "ESC123"

        mm_response = MagicMock()
        mm_response.status_code = 409
        mm_response.json.return_value = {'id': 'MMPC009'}
        self.processor.money_movement_client.make_post_request.return_value = mm_response

        self.processor.update_retry = MagicMock()
        self.processor.update_customer_status = MagicMock()

        self.processor.process_payment(data, 'customer', 100)

        # Must hit: update_customer_status(data, target, 'FF', amount=amount)
        self.processor.update_customer_status.assert_called_once()
        args, kwargs = self.processor.update_customer_status.call_args
        self.assertEqual(args[0], data)
        self.assertEqual(args[1], 'customer')
        self.assertEqual(args[2], 'FF')
        self.assertEqual(kwargs.get('amount'), 100)
        self.processor.update_retry.assert_not_called()

    @patch('app.main.init_validate_context')
    @patch('app.main.create_money_movement_request')
    @patch('app.main.extract_json_body')
    def test_process_payment_400_ful902_calls_update_retry(
        self, mock_extract_json, mock_create_request, mock_init_validate
    ):
        mock_init_validate.return_value = _noop_context()
        mock_create_request.return_value = MagicMock()

        data = {
            'customer_account_key': '123',
            'customer_retry_count': 1,
            'event_id': 'EVT-3',
            'referral_code': 'RC-3',
        }

        self.processor.tcr_client.get_account_escid.return_value = "ESC999"

        mm_response = MagicMock()
        mm_response.status_code = 400
        mm_response.json.return_value = {'id': 'ANY'}
        self.processor.money_movement_client.make_post_request.return_value = mm_response

        # Force: response_body.get('id') == 'FUL902'
        mock_extract_json.return_value = {'id': 'FUL902'}

        self.processor.update_retry = MagicMock()
        self.processor.update_customer_status = MagicMock()

        self.processor.process_payment(data, 'customer', 100)

        self.processor.update_retry.assert_called_once_with(data, 'customer')
        self.processor.update_customer_status.assert_not_called()
