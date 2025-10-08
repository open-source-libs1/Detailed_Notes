import json
import logging
from typing import Any, List, Sequence, Tuple

logger = logging.getLogger(__name__)

# Public type aliases for clarity
MsgTuple = Tuple[str, Any]   # (messageId, payload_object)
InTuple  = Tuple[str, str]   # (messageId, body_json_string)


def _load_body(body_str: str, *, msg_id: str):
    """
    Parse the outer SQS body JSON with a simple two-pass approach:
      1) strict parse
      2) lenient parse (strict=False) to tolerate raw control chars in strings
    """
    try:
        return json.loads(body_str)
    except json.JSONDecodeError as e1:
        logger.warning("Record (id=%s): strict JSON parse failed; retrying lenient (%s)", msg_id, e1)
        return json.loads(body_str, strict=False)


def extract_payloads(records: Sequence[InTuple]) -> List[MsgTuple]:
    """
    Extract payload objects from SQS body JSON strings.

    What it does
    ------------
    For each (messageId, body_json_string):
      1) Parse body_json_string (outer JSON) with strict→lenient fallback.
      2) Expect `body["records"]` to be a list of dicts with a `payload` field.
      3) `payload` must be a JSON string; parse it. Use strict→lenient fallback and trim whitespace.
      4) Return a flat list of (messageId, payload_object). Malformed entries are skipped with warnings.

    Parameters
    ----------
    records : Sequence[Tuple[str, str]]
        Built in the handler as: [(r["messageId"], r["body"]) for r in event["Records"]].

    Returns
    -------
    List[Tuple[str, Any]]
        [(messageId, payload_object), ...]
    """
    out: List[MsgTuple] = []
    logger.debug("extract_payloads: starting with %d record(s)", len(records))

    # Iterate each SQS item: contract is (messageId, body_json_string)
    for message_id, body_str in records:
        # Minimal defensive check to avoid surprising crashes
        if not isinstance(message_id, str) or not isinstance(body_str, str):
            logger.warning(
                "Record (id=%s): expected (str, str), got (%s, %s); skipping",
                message_id, type(message_id).__name__, type(body_str).__name__,
            )
            continue

        # 1) Decode the outer body JSON (strict→lenient)
        try:
            body = _load_body(body_str, msg_id=message_id)
        except json.JSONDecodeError as e:
            logger.warning("Record (id=%s): body is not valid JSON; skipping (%s)", message_id, e)
            continue

        # 2) Safely access inner list `records`
        body_records = body.get("records")  # None if missing
        if not isinstance(body_records, list):
            logger.warning("Record (id=%s): 'records' missing or not a list; skipping", message_id)
            continue

        logger.debug("Record (id=%s): found %d inner record(s)", message_id, len(body_records))

        # 3) Pull and decode each 'payload'
        for rec in body_records:
            if not isinstance(rec, dict) or "payload" not in rec:
                logger.warning("Record (id=%s): missing/invalid 'payload'; skipping", message_id)
                continue

            raw = rec["payload"]

            # Per contract: payload should be a JSON *string* (skip otherwise)
            if not isinstance(raw, str):
                logger.warning("Record (id=%s): payload is not a string; skipping", message_id)
                continue

            raw_str = raw.strip()  # whitespace around the JSON is fine

            # Try strict; if it fails, fallback to lenient (tolerates some control chars)
            try:
                payload = json.loads(raw_str)
            except json.JSONDecodeError as e1:
                logger.warning("Record (id=%s): strict payload parse failed; retrying lenient (%s)", message_id, e1)
                try:
                    payload = json.loads(raw_str, strict=False)
                except json.JSONDecodeError as e2:
                    logger.warning(
                        "Record (id=%s): payload not valid JSON; skipping (%s). Head=%r",
                        message_id, e2, raw_str[:120],
                    )
                    continue

            out.append((message_id, payload))

    logger.debug("extract_payloads: extracted %d payload(s) total", len(out))
    return out


# ---- Serialization helpers (used by handler) ----

def to_json_bytes(obj: Any) -> bytes:
    """Compact JSON → UTF-8 bytes (use for Kinesis Data=)."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def to_json_str(obj: Any) -> str:
    """Compact JSON → string (use for SQS MessageBody)."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
