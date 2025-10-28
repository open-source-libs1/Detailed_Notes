# tests/test_main.py
from types import SimpleNamespace
from src.main import app  # wherever your `app` object lives

EVENT_UUID = "924c2586-7958-4fce-8296-53c73076019e"
REQ_ID     = "req-123"

def _set_current_event(body: dict) -> None:
    class FakeEvent:
        def __init__(self, body):
            self.json_body = body
            self.request_context = {"requestId": REQ_ID}

    fe = FakeEvent(body)
    setattr(app, "current_event", fe)
    setattr(app, "lambda_context", SimpleNamespace(aws_request_id=EVENT_UUID))
