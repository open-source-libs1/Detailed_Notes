#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Build Lambda ZIP LOCALLY (no Docker pulls, no LocalStack pip installs)
#
# FIX INCLUDED:
#   - Ensure ZIP ROOT contains:
#       handler.py
#       src/...
#       aws_util.py (if present and imported)
#
# This directly fixes: "Unable to import module 'handler': No module named 'src'"
# =============================================================================

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${HERE_DIR}/.." && pwd)"

ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

# QSink forwarder lambda
QSINK_NAME="qsink-referrals-enrollment"
QSINK_PROJECT_DIR="${ROOT_DIR}/qsink-referrals-enrollment"
QSINK_HANDLER_PY="${QSINK_PROJECT_DIR}/handler.py"
QSINK_SRC_DIR="${QSINK_PROJECT_DIR}/src"
QSINK_AWS_UTIL_PY="${QSINK_PROJECT_DIR}/aws_util.py"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "============================================================"
echo " Building Lambda ZIPs (local, robust) "
echo "============================================================"
echo "ROOT_DIR        = ${ROOT_DIR}"
echo "ARTIFACT_DIR    = ${ARTIFACT_DIR}"
echo "BUILD_DIR       = ${BUILD_DIR}"
echo "QSINK_PROJECT   = ${QSINK_PROJECT_DIR}"
echo ""

command -v pipenv >/dev/null 2>&1 || { echo "ERROR: pipenv not found on host. Install pipenv first."; exit 1; }
command -v zip >/dev/null 2>&1 || { echo "ERROR: zip not found on host. Install zip first."; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERROR: python not found on host."; exit 1; }

build_lambda_from_pipenv() {
  local name="$1"
  local project_dir="$2"
  local handler_py="$3"
  local src_dir="$4"

  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local zip_path="${ARTIFACT_DIR}/${name}.zip"

  echo ""
  echo "---- Building '${name}' ----"
  echo "[${name}] Project dir : ${project_dir}"
  echo "[${name}] Handler py  : ${handler_py}"
  echo "[${name}] Source dir  : ${src_dir}"
  echo "[${name}] Build dir   : ${build_subdir}"
  echo "[${name}] Artifact    : ${zip_path}"
  echo ""

  [[ -d "${project_dir}" ]] || { echo "[${name}] ERROR: Project dir not found: ${project_dir}"; exit 1; }
  [[ -f "${handler_py}" ]] || { echo "[${name}] ERROR: handler.py not found: ${handler_py}"; exit 1; }
  [[ -d "${src_dir}" ]] || { echo "[${name}] ERROR: src/ dir not found: ${src_dir}"; exit 1; }

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  (
    set -euo pipefail
    cd "${project_dir}"

    echo "[${name}] Step 1: pipenv install (sync to Pipfile.lock)"
    pipenv install

    echo "[${name}] Step 2: Generate deterministic requirements snapshot -> ${req_file}"
    if pipenv --help 2>/dev/null | grep -q "requirements"; then
      pipenv requirements > "${req_file}"
    else
      pipenv run python -m pip freeze > "${req_file}"
    fi

    echo "[${name}] Requirements snapshot (first 25 lines):"
    head -n 25 "${req_file}" || true
    echo ""

    echo "[${name}] Step 3: Install deps into build dir via pip --target"
    pipenv run python -m pip install \
      --disable-pip-version-check \
      --no-input \
      --no-compile \
      -r "${req_file}" \
      -t "${build_subdir}"

    echo "[${name}] Step 4: Copy lambda source into build dir"
    # IMPORTANT CHANGE:
    #   - Copy handler.py to ZIP root
    #   - Copy src/ directory as a directory to ZIP root (so imports from src.* work)
    cp "${handler_py}" "${build_subdir}/handler.py"
    cp -R "${src_dir}" "${build_subdir}/src"

    # Optional but safe: if aws_util.py exists (your handler imports it), include it at ZIP root.
    if [[ -f "${QSINK_AWS_UTIL_PY}" ]]; then
      cp "${QSINK_AWS_UTIL_PY}" "${build_subdir}/aws_util.py"
      echo "[${name}] Included aws_util.py at ZIP root."
    else
      echo "[${name}] NOTE: aws_util.py not found at ${QSINK_AWS_UTIL_PY} (skipping)."
    fi
  )

  echo "[${name}] Step 5: Optional cleanup (smaller ZIP, safe)"
  rm -rf "${build_subdir}/__pycache__" || true
  find "${build_subdir}" -name "*.pyc" -delete || true

  echo "[${name}] Step 6: Create ZIP -> ${zip_path}"
  rm -f "${zip_path}"
  (
    cd "${build_subdir}"
    zip -qr "${zip_path}" .
  )

  echo "[${name}] DONE"
  echo "[${name}] Artifact size:"
  ls -lh "${zip_path}" || true
  echo ""

  echo "[${name}] Debug verify: ZIP must contain handler.py AND src/ at root"
  unzip -l "${zip_path}" | egrep '(^\s+.*\s+handler\.py$|^\s+.*\s+src/)' | head -n 80 || true
  echo ""
}

build_lambda_from_pipenv "${QSINK_NAME}" "${QSINK_PROJECT_DIR}" "${QSINK_HANDLER_PY}" "${QSINK_SRC_DIR}"

echo "============================================================"
echo " Build complete "
echo "============================================================"
echo "Artifacts:"
ls -lh "${ARTIFACT_DIR}" || true
echo ""
echo "Requirements snapshots:"
ls -lh "${BUILD_DIR}"/requirements_*.txt || true
echo ""



//////////////////////////////



#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] Starting LocalStack enrollment deployment script ====="

# Prefer awslocal inside LocalStack container
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL=(awslocal)
  echo "===== [bootstrap] Using 'awslocal'"
else
  # Fallback; inside container, LocalStack edge is typically localhost:4566
  AWSLOCAL=(aws --endpoint-url="http://localhost:4566")
  echo "===== [bootstrap] 'awslocal' not found, using aws --endpoint-url=http://localhost:4566"
fi

# Load env file if present (inside container this is typically mounted to /project)
ENV_FILE="/project/.env.localstack"
if [[ -f "${ENV_FILE}" ]]; then
  echo "===== [bootstrap] Loading environment from ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "===== [bootstrap] [WARN] ${ENV_FILE} not found; using defaults where possible"
fi

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

# Your handler imports expect this env var for destination queue
DEST_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME}"

SECRET_NAME="${SECRET_ARN:-enrollment-db-local}"

ARTIFACT_DIR="/artifacts"
QSINK_ZIP="${ARTIFACT_DIR}/qsink-referrals-enrollment.zip"

FUNCTION_NAME="qsink-forwarder-lambda"
HANDLER_PATH="handler.lambda_handler"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/lambda-role"

echo "===== [bootstrap] Effective configuration ====="
echo "AWS_REGION            = ${AWS_REGION}"
echo "QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "SECRET_NAME           = ${SECRET_NAME}"
echo "ARTIFACT_DIR          = ${ARTIFACT_DIR}"
echo "QSINK_ZIP             = ${QSINK_ZIP}"
echo "FUNCTION_NAME         = ${FUNCTION_NAME}"
echo "HANDLER_PATH          = ${HANDLER_PATH}"
echo "ROLE_ARN              = ${ROLE_ARN}"
echo ""

# Basic artifact validation + debug listing
if [[ ! -f "${QSINK_ZIP}" ]]; then
  echo "===== [bootstrap] ERROR: Lambda ZIP not found at ${QSINK_ZIP}"
  echo "===== [bootstrap] Ensure you mounted artifacts into the LocalStack container."
  exit 1
fi

echo "===== [bootstrap] ZIP debug check (must contain handler.py and src/ at root) ====="
unzip -l "${QSINK_ZIP}" | egrep '(^\s+.*\s+handler\.py$|^\s+.*\s+src/)' | head -n 80 || true
echo ""

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
get_or_create_queue_url() {
  local qname="$1"
  local qurl=""

  set +e
  qurl="$("${AWSLOCAL[@]}" sqs get-queue-url --queue-name "${qname}" --query 'QueueUrl' --output text 2>/dev/null)"
  set -e

  if [[ -z "${qurl}" || "${qurl}" == "None" ]]; then
    echo "===== [bootstrap] Queue ${qname} not found; creating (idempotent-safe) ====="
    "${AWSLOCAL[@]}" sqs create-queue --queue-name "${qname}" >/dev/null
    qurl="$("${AWSLOCAL[@]}" sqs get-queue-url --queue-name "${qname}" --query 'QueueUrl' --output text)"
  else
    echo "===== [bootstrap] Queue ${qname} exists ====="
  fi

  echo "${qurl}"
}

# -----------------------------------------------------------------------------
# Create S3 bucket (optional for your flow, but safe)
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if needed) ====="
"${AWSLOCAL[@]}" s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] Bucket ${QSINK_BUCKET_NAME} may already exist; continuing ====="

# -----------------------------------------------------------------------------
# Create/resolve SQS queues and ARNs
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Resolving queues ====="
QSINK_QUEUE_URL="$(get_or_create_queue_url "${QSINK_QUEUE_NAME}")"
DEST_QUEUE_URL="$(get_or_create_queue_url "${DEST_QUEUE_NAME}")"

QSINK_QUEUE_ARN="$("${AWSLOCAL[@]}" sqs get-queue-attributes \
  --queue-url "${QSINK_QUEUE_URL}" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)"

echo "QSINK_QUEUE_URL = ${QSINK_QUEUE_URL}"
echo "DEST_QUEUE_URL  = ${DEST_QUEUE_URL}"
echo "QSINK_QUEUE_ARN = ${QSINK_QUEUE_ARN}"
echo ""

# -----------------------------------------------------------------------------
# Create or update DB secret (only if DB_* vars exist; otherwise skip safely)
# -----------------------------------------------------------------------------
if [[ -n "${DB_HOST:-}" && -n "${DB_PORT:-}" && -n "${DB_NAME:-}" && -n "${DB_USER:-}" && -n "${DB_PASSWORD:-}" ]]; then
  echo "===== [bootstrap] Creating/updating Secrets Manager secret '${SECRET_NAME}' ====="

  DB_SECRET_JSON="$(python - <<PY
import json, os
print(json.dumps({
  "host": os.environ["DB_HOST"],
  "port": os.environ["DB_PORT"],
  "dbname": os.environ["DB_NAME"],
  "username": os.environ["DB_USER"],
  "password": os.environ["DB_PASSWORD"],
}))
PY
)"

  if "${AWSLOCAL[@]}" secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
    echo "===== [bootstrap] Secret exists; updating value ====="
    "${AWSLOCAL[@]}" secretsmanager put-secret-value \
      --secret-id "${SECRET_NAME}" \
      --secret-string "${DB_SECRET_JSON}" >/dev/null
  else
    echo "===== [bootstrap] Secret not found; creating ====="
    "${AWSLOCAL[@]}" secretsmanager create-secret \
      --name "${SECRET_NAME}" \
      --secret-string "${DB_SECRET_JSON}" >/dev/null
  fi
else
  echo "===== [bootstrap] [WARN] DB_* variables not fully set; skipping secret creation safely ====="
fi

# -----------------------------------------------------------------------------
# Deploy Lambda (create or update)
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Deploying Lambda '${FUNCTION_NAME}' ====="

# Keep env vars simple & debug-friendly.
# IMPORTANT: DESTINATION_SQS_QUEUE_URL is used by your handler.
ENV_JSON="Variables={
  APP_ENV=local,
  LOG_LEVEL=DEBUG,
  AWS_DEFAULT_REGION=${AWS_REGION},
  QSINK_BUCKET_NAME=${QSINK_BUCKET_NAME},
  QSINK_QUEUE_NAME=${QSINK_QUEUE_NAME},
  ENROLLMENT_QUEUE_NAME=${ENROLLMENT_QUEUE_NAME},
  DESTINATION_SQS_QUEUE_URL=${DEST_QUEUE_URL},
  ENABLE_CROSS_ACCOUNT_CARD_INTEGRATION=false
}"

if "${AWSLOCAL[@]}" lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  echo "===== [bootstrap] Lambda exists; updating code ====="
  "${AWSLOCAL[@]}" lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${QSINK_ZIP}" >/dev/null

  echo "===== [bootstrap] Updating configuration (handler + env) ====="
  "${AWSLOCAL[@]}" lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --handler "${HANDLER_PATH}" \
    --runtime python3.12 \
    --role "${ROLE_ARN}" \
    --timeout 30 \
    --environment "${ENV_JSON}" >/dev/null
else
  echo "===== [bootstrap] Lambda not found; creating ====="
  "${AWSLOCAL[@]}" lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --runtime python3.12 \
    --handler "${HANDLER_PATH}" \
    --zip-file "fileb://${QSINK_ZIP}" \
    --role "${ROLE_ARN}" \
    --timeout 30 \
    --environment "${ENV_JSON}" >/dev/null
fi

echo "===== [bootstrap] Lambda config (debug) ====="
"${AWSLOCAL[@]}" lambda get-function-configuration --function-name "${FUNCTION_NAME}" --output json | head -n 140 || true
echo ""

# -----------------------------------------------------------------------------
# Wire SQSQ1 -> Lambda via event source mapping
# -----------------------------------------------------------------------------
echo "===== [bootstrap] Ensuring SQS -> Lambda event source mapping exists ====="
EXISTING_UUID="$("${AWSLOCAL[@]}" lambda list-event-source-mappings \
  --function-name "${FUNCTION_NAME}" \
  --query "EventSourceMappings[?EventSourceArn=='${QSINK_QUEUE_ARN}'].UUID | [0]" \
  --output text || true)"

if [[ -z "${EXISTING_UUID}" || "${EXISTING_UUID}" == "None" ]]; then
  echo "===== [bootstrap] Creating event source mapping: ${QSINK_QUEUE_NAME} -> ${FUNCTION_NAME} ====="
  "${AWSLOCAL[@]}" lambda create-event-source-mapping \
    --function-name "${FUNCTION_NAME}" \
    --event-source-arn "${QSINK_QUEUE_ARN}" \
    --batch-size 1 \
    --enabled >/dev/null
else
  echo "===== [bootstrap] Event source mapping already exists: ${EXISTING_UUID} ====="
fi

echo "===== [bootstrap] Current event source mappings ====="
"${AWSLOCAL[@]}" lambda list-event-source-mappings --function-name "${FUNCTION_NAME}" --output table || true
echo ""

echo "===== [bootstrap] Deployment Summary ====="
echo "QSink bucket        : ${QSINK_BUCKET_NAME}"
echo "QSink queue (src)   : ${QSINK_QUEUE_NAME}"
echo "Enrollment queue    : ${ENROLLMENT_QUEUE_NAME}"
echo "Lambda function     : ${FUNCTION_NAME}"
echo "Handler             : ${HANDLER_PATH}"
echo "Dest queue url env  : DESTINATION_SQS_QUEUE_URL=${DEST_QUEUE_URL}"
echo "===== [bootstrap] Deployment complete ====="

