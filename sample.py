# --- Resolve IDs (ALB safe) + detailed logging --------------------
headers = (getattr(app.current_event, "headers", {}) or {})

# ALB puts the trace id in header; parse Root=...
trace_hdr = headers.get("x-amzn-trace-id") or headers.get("X-Amzn-Trace-Id") or ""
trace_root = None
if trace_hdr:
    for part in trace_hdr.split(";"):
        part = part.strip()
        if part.startswith("Root="):
            trace_root = part[5:]
            break

event_id = app.lambda_context.aws_request_id                 # Lambda invocation id (UUID)
correlation_id = trace_root or event_id                       # Prefer trace Root=..., else fallback

# Add to log context for the rest of the invocation
try:
    logger.append_keys(correlation_id=correlation_id, event_id=event_id)
except Exception:
    pass  # keep logs resilient in local/unit-test runs

# Very explicit debug trail
logger.info(f"headers_present={bool(headers)}")
logger.info(f"x_amzn_trace_id='{trace_hdr}'")
logger.info(f"trace_root_parsed='{trace_root}'")
logger.info(
    f"chosen_ids correlation_id='{correlation_id}' event_id='{event_id}' "
    f"used_trace_root={bool(trace_root)} used_fallback={not bool(trace_root)}"
)
