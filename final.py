############################################
# App / Local run
############################################
APP_ENV=local
LOG_LEVEL=INFO

############################################
# AWS / LocalStack basics
############################################
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1

# IMPORTANT:
# - Your containers should use: http://localstack:4566
# - Your host machine should use: http://localhost:4566
AWS_ENDPOINT_URL=http://localstack:4566

# This is what your app uses as SecretId (your logs show you pass SECRET_ARN=enrollment-db-local)
SECRET_ARN=enrollment-db-local

############################################
# Local resource names (bootstrap must match)
############################################
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

############################################
# DB connection details (real DEV values)
# Bootstrap will convert these into the secret JSON automatically.
############################################
DB_HOST=my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=enrollment
DB_USER=enrollment_dev
DB_PASSWORD=super-secret-password

############################################
# Proxy / CA (only if your environment needs it)
# If LocalStack Pro activation fails with 407, your proxy likely needs credentials.
############################################
HTTP_PROXY=
HTTPS_PROXY=

# Do NOT proxy localstack/localhost traffic
NO_PROXY=localhost,127.0.0.1,localstack,*.localstack,169.254.169.254

# If you mount a corporate CA cert into LocalStack and the app container, point to it here.
# Leave blank if you are not mounting certs.
REQUESTS_CA_BUNDLE=
CURL_CA_BUNDLE=
NODE_EXTRA_CA_CERTS=

############################################
# LocalStack Pro
############################################
# Required if you want Pro features; if blank, Pro activation may fail (or fall back depending on image/setup).
LOCALSTACK_API_KEY=





//////////////////////////////////


services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack:latest
    container_name: localstack-enrollment
    ports:
      - "127.0.0.1:4566:4566"          # LocalStack Gateway
      - "127.0.0.1:4510-4559:4510-4559" # External services port range
      - "127.0.0.1:443:443"            # HTTPS Gateway (often used by Pro)
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      # Keep services list close to what you already used (safe & consistent)
      - SERVICES=s3,sqs,secretsmanager,lambda,iam,sts,logs,cloudformation
      - DEBUG=1

      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}

      # Pro key (if set)
      - LOCALSTACK_API_KEY=${LOCALSTACK_API_KEY}

      # Proxy / CA (pass-through; harmless when blank)
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - REQUESTS_CA_BUNDLE=${REQUESTS_CA_BUNDLE}
      - CURL_CA_BUNDLE=${CURL_CA_BUNDLE}
      - NODE_EXTRA_CA_CERTS=${NODE_EXTRA_CA_CERTS}

      # LocalStack runtime essentials (matches patterns you already had)
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LOCALSTACK_HOSTNAME=localstack
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=60

      # Useful for anything inside LocalStack that needs the edge URL
      - AWS_ENDPOINT_URL=http://localstack:4566

    volumes:
      # Repo mounted so bootstrap can read /project/.env
      - ./:/project

      # Your boot script (do NOT rename)
      - ./deploy.enrollment-init.sh:/etc/localstack/init/ready.d/deploy.enrollment-init.sh

      # Needed for lambda docker runtime
      - /var/run/docker.sock:/var/run/docker.sock

      # Optional cert mount (only if you actually have ./certs)
      # - ./certs:/opt/certs:ro

    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:4566/_localstack/health"]
      interval: 20s
      timeout: 10s
      retries: 15
      start_period: 30s

  enrollment-writer:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: enrollment-writer
    depends_on:
      localstack:
        condition: service_healthy

    environment:
      - APP_ENV=${APP_ENV}
      - LOG_LEVEL=${LOG_LEVEL}

      # AWS -> LocalStack
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}
      - AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL}
      - AWS_ACCESS_KEY_ID=localstack
      - AWS_SECRET_ACCESS_KEY=localstack

      # Secret name/id your app uses (keep same)
      - SECRET_ARN=${SECRET_ARN}

      # Keep DB_* as-is (you currently see them in logs; doesn’t hurt)
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}

      # Proxy / CA (pass-through)
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - REQUESTS_CA_BUNDLE=${REQUESTS_CA_BUNDLE}
      - CURL_CA_BUNDLE=${CURL_CA_BUNDLE}
      - NODE_EXTRA_CA_CERTS=${NODE_EXTRA_CA_CERTS}

    restart: unless-stopped




///////////////////////////



#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] Starting LocalStack enrollment init... ====="

ENV_FILE="/project/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found. Expected repo mounted to /project."
  exit 1
fi

# Load .env safely (no 'source' so JSON/quotes don't break).
# Supports simple KEY=VALUE lines.
while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip comments/blank
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" =~ ^[[:space:]]*$ ]] && continue

  # Only process KEY=VALUE
  if [[ "$line" == *"="* ]]; then
    key="${line%%=*}"
    value="${line#*=}"

    # Trim spaces
    key="$(echo -n "$key" | xargs)"
    value="$(echo -n "$value" | xargs)"

    export "${key}=${value}"
  fi
done < "${ENV_FILE}"

AWS_REGION="${AWS_REGION:-us-east-1}"
QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"
SECRET_ARN="${SECRET_ARN:-enrollment-db-local}"

DB_HOST="${DB_HOST:-}"
DB_PORT="${DB_PORT:-}"
DB_NAME="${DB_NAME:-}"
DB_USER="${DB_USER:-}"
DB_PASSWORD="${DB_PASSWORD:-}"

echo "===== [bootstrap] Effective configuration ====="
echo "AWS_REGION            = ${AWS_REGION}"
echo "QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "SECRET_ARN            = ${SECRET_ARN}"
echo "DB_HOST               = ${DB_HOST}"
echo "DB_PORT               = ${DB_PORT}"
echo "DB_NAME               = ${DB_NAME}"
echo "DB_USER               = ${DB_USER}"
echo "DB_PASSWORD           = (hidden)"

# Validate required DB inputs (so we fail fast with clear message)
if [[ -z "${DB_HOST}" || -z "${DB_PORT}" || -z "${DB_NAME}" || -z "${DB_USER}" || -z "${DB_PASSWORD}" ]]; then
  echo "ERROR: DB_* values are missing in .env. Please set DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD."
  exit 1
fi

# Build DB secret JSON exactly in the format your app expects
DB_SECRET_JSON="{\"host\":\"${DB_HOST}\",\"port\":\"${DB_PORT}\",\"dbname\":\"${DB_NAME}\",\"username\":\"${DB_USER}\",\"password\":\"${DB_PASSWORD}\"}"

echo "===== [bootstrap] DB secret JSON (safe view) ====="
echo "${DB_SECRET_JSON}" | sed -E 's/"password":"[^"]+"/"password":"***"/'

AWSLOCAL="awslocal --region ${AWS_REGION}"

echo "===== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if needed) ====="
if ${AWSLOCAL} s3api head-bucket --bucket "${QSINK_BUCKET_NAME}" >/dev/null 2>&1; then
  echo "[bootstrap] S3 bucket already exists."
else
  ${AWSLOCAL} s3api create-bucket --bucket "${QSINK_BUCKET_NAME}" >/dev/null
  echo "[bootstrap] S3 bucket created."
fi

echo "===== [bootstrap] Creating SQS queues '${QSINK_QUEUE_NAME}' and '${ENROLLMENT_QUEUE_NAME}' (if needed) ====="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null
${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null

QSINK_QUEUE_URL="$(${AWSLOCAL} sqs get-queue-url --queue-name "${QSINK_QUEUE_NAME}" --query 'QueueUrl' --output text)"
ENROLLMENT_QUEUE_URL="$(${AWSLOCAL} sqs get-queue-url --queue-name "${ENROLLMENT_QUEUE_NAME}" --query 'QueueUrl' --output text)"

echo "[bootstrap] QSINK_QUEUE_URL      = ${QSINK_QUEUE_URL}"
echo "[bootstrap] ENROLLMENT_QUEUE_URL = ${ENROLLMENT_QUEUE_URL}"

echo "===== [bootstrap] Creating/updating Secrets Manager secret '${SECRET_ARN}' ====="
if ${AWSLOCAL} secretsmanager describe-secret --secret-id "${SECRET_ARN}" >/dev/null 2>&1; then
  ${AWSLOCAL} secretsmanager put-secret-value \
    --secret-id "${SECRET_ARN}" \
    --secret-string "${DB_SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret updated."
else
  ${AWSLOCAL} secretsmanager create-secret \
    --name "${SECRET_ARN}" \
    --secret-string "${DB_SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret created."
fi

echo "===== [bootstrap] Setup complete ====="

