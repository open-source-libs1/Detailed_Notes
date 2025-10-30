# db_util/tests/test_fulfillment_event_queries.py
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from pydantic import ValidationError

from db_util.schemas import FulfillmentEventCreate
from db_util.queries import insert_fulfillment_event, INSERT_FULFILLMENT_EVENT_SQL


@patch('db_util.queries.connection')  # keep consistent with existing tests
class TestInsertFulfillmentEvent(unittest.TestCase):
    def setUp(self) -> None:
        # connection + cursor behave as context managers
        self.mock_conn = MagicMock(name='conn')
        self.mock_conn.__enter__.return_value = self.mock_conn
        self.mock_conn.__exit__.return_value = None
        self.mock_cur = MagicMock(name='cursor')
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cur

        # a valid event payload (min fields to insert)
        self.valid_evt = FulfillmentEventCreate(
            correlation_id='corr-1',
            prospect_account_key='pkey-001',
            prospect_account_key_type='CRM',
            prospect_sor_id=1,                # SMALLINT (nullable)
            internal_program_key=123456789,   # BIGINT (kept as int)
            referral_code='REFL1234',
            customer_fulfillment_reference_id=None,
            customer_fulfillment_reference_source_id=None,
            tenant_id=1,                      # SMALLINT
            creation_user_id='fulfillment-lambda',
            last_updated_user_id='fulfillment-lambda',
            event_id=uuid4(),
        )

    @patch('db_util.queries.logger')
    def test_insert_fulfillment_event_success(self, _mock_logger, _mock_conn_type):
        # arrange
        self.mock_cur.fetchone.return_value = ['REFL1234']

        # act
        got = insert_fulfillment_event(self.mock_conn, self.valid_evt)

        # assert
        self.assertEqual(got, 'REFL1234')
        self.mock_conn.cursor.assert_called_once()
        self.mock_cur.execute.assert_called_once()
        sql, params = self.mock_cur.execute.call_args.args
        self.assertEqual(sql, INSERT_FULFILLMENT_EVENT_SQL)
        # spot-check parameter ordering
        self.assertEqual(params[0], self.valid_evt.correlation_id)
        self.assertEqual(params[4], self.valid_evt.internal_program_key)
        self.assertEqual(params[5], self.valid_evt.referral_code)
        self.assertEqual(params[8], self.valid_evt.tenant_id)
        self.assertEqual(params[-1], self.valid_evt.event_id)

    @patch('db_util.queries.logger')
    def test_insert_fulfillment_event_no_row_raises(self, _mock_logger, _mock_conn_type):
        # no row returned from RETURNING
        self.mock_cur.fetchone.return_value = None
        with self.assertRaises(RuntimeError):
            insert_fulfillment_event(self.mock_conn, self.valid_evt)

    @patch('db_util.queries.logger')
    def test_insert_fulfillment_event_execute_failure_raises(self, _mock_logger, _mock_conn_type):
        self.mock_cur.execute.side_effect = Exception('boom')
        with self.assertRaises(Exception):
            insert_fulfillment_event(self.mock_conn, self.valid_evt)

    # ---- Model validation specific to our smallint bounds (no conint used) ----

    def test_model_validation_tenant_id_too_large(self, _mock_conn_type):
        bad = self.valid_evt.model_dump()
        bad['tenant_id'] = 40000  # > 32767
        with self.assertRaises(ValidationError):
            FulfillmentEventCreate(**bad)

    def test_model_validation_prospect_sor_id_negative(self, _mock_conn_type):
        bad = self.valid_evt.model_dump()
        bad['prospect_sor_id'] = -1  # < 0
        with self.assertRaises(ValidationError):
            FulfillmentEventCreate(**bad)

    def test_model_accepts_optional_nullables(self, _mock_conn_type):
        evt = FulfillmentEventCreate(
            correlation_id='corr-2',
            prospect_account_key=None,
            prospect_account_key_type=None,
            prospect_sor_id=None,            # nullable smallint
            internal_program_key=9876543210,
            referral_code='REFZ9999',
            customer_fulfillment_reference_id=None,
            customer_fulfillment_reference_source_id=None,
            tenant_id=10,
            creation_user_id='u1',
            last_updated_user_id='u1',
            event_id=uuid4(),
        )
        # Should construct without raising
        self.assertEqual(evt.tenant_id, 10)
