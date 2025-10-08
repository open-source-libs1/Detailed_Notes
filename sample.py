import json
import logging
from typing import Any, List, Sequence, Tuple

logger = logging.getLogger(__name__)

# Public type aliases for clarity
MsgTuple = Tuple[str, Any]   # (messageId, payload_object)
InTuple  = Tuple[str, str]   # (messageId, body_json_string)


def extract_payloads(records: Sequence[InTuple]) -> List[MsgTuple]:
    """
    Extract payload objects from SQS body JSON strings.

    For each (messageId, body_json_string):
      1) Parse body_json_string (outer JSON) after trimming leading/trailing whitespace.
      2) Expect body["records"] to be a list of objects with a `payload` field.
      3) `payload` must be a JSON string; trim it and parse (strict → lenient fallback).
      4) Return a flat list of (messageId, payload_object).

    Returns: [(messageId, payload_object)], skipping malformed entries with warnings.
    """
    out: List[MsgTuple] = []
    logger.debug("extract_payloads: starting with %d record(s)", len(records))

    for message_id, body_str in records:
        # Minimal sanity check to avoid surprises
        if not isinstance(message_id, str) or not isinstance(body_str, str):
            logger.warning(
                "Record (id=%s): expected (str, str), got (%s, %s); skipping",
                message_id, type(message_id).__name__, type(body_str).__name__,
            )
            continue

        # ---- 1) Decode the outer body JSON (after trimming) ----
        try:
            body = json.loads(body_str.strip())
        except (TypeError, ValueError) as e:
            logger.warning("Record (id=%s): body is not valid JSON; skipping (%s)", message_id, e)
            continue

        # 2) Access inner 'records'
        body_records = body.get("records")
        if not isinstance(body_records, list):
            logger.warning("Record (id=%s): 'records' missing or not a list; skipping", message_id)
            continue

        logger.debug("Record (id=%s): found %d inner record(s)", message_id, len(body_records))

        # ---- 3) Each 'payload' must be a JSON string → trim and parse ----
        for rec in body_records:
            if not isinstance(rec, dict) or "payload" not in rec:
                logger.warning("Record (id=%s): missing/invalid 'payload'; skipping", message_id)
                continue

            raw = rec["payload"]
            if not isinstance(raw, str):
                logger.warning("Record (id=%s): payload is not a string; skipping", message_id)
                continue

            raw_str = raw.strip()  # removes leading/trailing spaces, \r, \n, NBSP, etc.

            try:
                payload = json.loads(raw_str)  # strict first
            except json.JSONDecodeError as e1:
                logger.warning("Record (id=%s): strict payload parse failed; retrying lenient (%s)", message_id, e1)
                try:
                    payload = json.loads(raw_str, strict=False)  # tolerate some control chars in strings
                except json.JSONDecodeError as e2:
                    logger.warning("Record (id=%s): payload not valid JSON; skipping (%s)", message_id, e2)
                    continue

            out.append((message_id, payload))

    logger.debug("extract_payloads: extracted %d payload(s) total", len(out))
    return out


# ---- Serialization helpers (shared by handler/tests) ----

def to_json_bytes(obj: Any) -> bytes:
    """
    Convert an object to compact JSON UTF-8 bytes.
    - Use for Kinesis `Data=` which requires bytes.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def to_json_str(obj: Any) -> str:
    """
    Convert an object to a compact JSON string.
    - Use for SQS MessageBody which requires a string.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
