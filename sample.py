    # ... your other asserts ...
    # 2) event_id sent to SQL is a string (adapter boundary)
    self.assertIsInstance(params[-1], str)
    self.assertEqual(params[-1], str(self.valid_evt.event_id))
    # Optional: sanity that it’s a valid UUID string
    self.assertEqual(UUID(params[-1]), self.valid_evt.event_id)
