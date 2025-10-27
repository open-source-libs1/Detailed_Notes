



from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Tuple

from db_util.connection import create_connection
from src.utils.database_utils import fetch_db_params_from_secret

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Parameterized SQL with RETURNING
_SQL = """
INSERT INTO fulfillment_event
 (prospect_account_key,
  prospect_account_key_type,
  sor_id,
  program_code,
  referral_code,
  referral_reference_keys)
VALUES (%s, %s, %s, %s, %s, %s::jsonb)
RETURNING referral_id;
""".strip()


def _get_db_params() -> Tuple[str, str, str, str, int]:
    """
    Prefer explicit environment variables (great for tests/CI/local).
    Fall back to Secrets Manager only when env vars aren't present.
    """
    need = ("DB_NAME", "DB_USERNAME", "DB_PASSWORD", "DB_HOST", "DB_PORT")
    env = os.environ
    if all(k in env for k in need):
        try:
            port = int(env["DB_PORT"])
        except Exception as exc:
            raise ValueError("DB_PORT must be an integer") from exc
        return env["DB_NAME"], env["DB_USERNAME"], env["DB_PASSWORD"], env["DB_HOST"], port

    # Fallback: fetch from Secrets Manager (prod path)
    name, user, pwd, host, port = fetch_db_params_from_secret()
    return name, user, pwd, host, int(port)


def create_referral_fulfillment(payload: Dict[str, Any], retries: int = 5) -> str:
    # Gather connection params
    db_name, db_user, db_password, db_host, db_port = _get_db_params()

    # Prepare bind parameters in a fixed order
    params = [
        payload["prospectAccountKey"],
        payload["prospectAccountKeyType"],
        payload["sorId"],
        payload["programCode"],
        payload["referralCode"],
        json.dumps(payload.get("referralReferenceKeys", [])),
    ]

    last_err: Exception | None = None

    # retry loop
    for attempt in range(1, retries + 1):
        conn = None
        cur = None
        try:
            logger.info(
                "db-connect attempt=%s host=%s db=%s user=%s",
                attempt, db_host, db_name, db_user
            )
            conn = create_connection(
                db_name=db_name,
                db_user=db_user,
                db_password=db_password,
                db_host=db_host,
                db_port=db_port,
            )

            with conn:  # commit/rollback via connection context manager
                cur = conn.cursor()
                cur.execute(_SQL, params)
                row = cur.fetchone()
                if not row or not row[0]:
                    # The INSERT ran but didn’t produce an id ⇒ treat as failure
                    raise RuntimeError("DB returned no referral_id")
                rid = str(row[0])
                logger.info("db-insert success attempt=%s referral_id=%s", attempt, rid)
                return rid

        except Exception as e:
            last_err = e
            logger.warning("db-insert failure attempt=%s err=%r", attempt, e)
            if attempt < retries:
                # tiny backoff with cap to keep lambdas snappy in tests
                time.sleep(min(0.2 * attempt, 1.0))
        finally:
            # release resources (safe even if context manager already handled it)
            try:
                if cur is not None:
                    cur.close()
            except Exception as e:
                logger.debug("cursor.close ignored: %r", e)
            try:
                if conn is not None:
                    conn.close()
            except Exception as e:
                logger.debug("conn.close ignored: %r", e)

    # all attempts failed
    assert last_err is not None
    logger.error("db-insert exhausted retries=%s last_err=%r", retries, last_err)
    raise last_err




####################################


from __future__ import annotations
import os
import boto3
import ast
from aws_util import retrieve_secret_value
from typing import Tuple

def fetch_db_params_from_secret() -> Tuple[str, str, str, str, int]:
    """
    Fetches credentials stored in AWS Secrets Manager.
    Returns (dbname, username, password, host, port) with port as int.
    """
    # Allow region via env if present; prod usually sets one of these.
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    secrets_manager = boto3.client("secretsmanager", region_name=region)

    secret_name = os.environ["DB_SECRET_ARN"]
    raw = retrieve_secret_value(secrets_manager, secret_name)

    try:
        secret = ast.literal_eval(raw) if raw is not None else None
    except (ValueError, SyntaxError):
        secret = None

    if not secret:
        raise ValueError(f"Failed to retrieve secret for {secret_name}")

    port = secret["port"]
    try:
        port = int(port)
    except Exception:
        # Let create_connection decide if it accepts non-int ports; int preferred.
        pass

    return (
        secret["dbname"],
        secret["username"],
        secret["password"],
        secret["host"],
        port,
    )

