############################################
# LocalStack Pro
############################################
# Use whichever your org uses (both are safe to keep; Pro will pick what it needs)
LOCALSTACK_API_KEY=
LOCALSTACK_AUTH_TOKEN=
ACTIVATE_PRO=1

############################################
# AWS / region
############################################
AWS_DEFAULT_REGION=us-east-1
AWS_REGION=us-east-1

# Host machine uses localhost; containers should use "http://localstack:4566"
AWS_ENDPOINT_URL=http://localstack:4566

# LocalStack dummy creds (safe for LocalStack)
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack

############################################
# App toggles
############################################
APP_ENV=local
LOG_LEVEL=INFO

# IMPORTANT: your logs showed "COF_SM_ENABLED is not set to true"
# Setting this makes enrollment-writer actually use Secrets Manager.
COF_SM_ENABLED=true

############################################
# Resource names (bootstrap must match)
############################################
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

# This must match what your code reads as SecretId/SECRET_ARN
SECRET_ARN=enrollment-db-local

############################################
# DB connection details (DEV)
############################################
DB_HOST=my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=enrollment
DB_USER=enrollment_dev
DB_PASSWORD=super-secret-password

# If you prefer to provide it directly (your requested format), you can set this too.
# If set, bootstrap uses it as-is.
DB_SECRET_JSON={"host":"my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com","port":"5432","dbname":"enrollment","username":"enrollment_dev","password":"super-secret-password"}

############################################
# Proxies (only if required)
############################################
HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=127.0.0.1,localhost,localstack,*.localstack,169.254.169.254

############################################
# Corporate CA bundles (keep as your current working values/paths)
############################################
REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt



//////////////////////////


services:
  localstack:
    # Keep Pro 4.8.x explicitly (no "latest")
    image: localstack/localstack-pro:4.8.1
    container_name: localstack-enrollment
    ports:
      - "127.0.0.1:4566:4566"            # LocalStack gateway
      - "127.0.0.1:4510-4559:4510-4559"  # external services port range
      - "127.0.0.1:443:443"              # HTTPS gateway (Pro often uses this)
    extra_hosts:
      - "host.docker.internal:host-gateway"

    # Keep the healthcheck (you explicitly asked not to remove it)
    healthcheck:
      test: [ "CMD", "curl", "-sf", "http://localhost:4566/_localstack/health" ]
      interval: 20s
      timeout: 10s
      retries: 15
      start_period: 30s

    environment:
      # Services list: keep close to your working config
      - SERVICES=cloudformation,iam,lambda,logs,ec2,secretsmanager,s3,apigateway,dynamodb,sns,sqs,sts,kinesis

      # Pro activation (keep what you had)
      - ACTIVATE_PRO=${ACTIVATE_PRO}
      - LOCALSTACK_API_KEY=${LOCALSTACK_API_KEY}
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      # Proxy settings (same pattern as your other team)
      - OUTBOUND_HTTP_PROXY=${HTTP_PROXY}
      - OUTBOUND_HTTPS_PROXY=${HTTPS_PROXY}

      # CA bundles (you said these were removed — keep them)
      - REQUESTS_CA_BUNDLE=${REQUESTS_CA_BUNDLE}
      - CURL_CA_BUNDLE=${CURL_CA_BUNDLE}
      - NODE_EXTRA_CA_CERTS=${NODE_EXTRA_CA_CERTS}

      # Debug and docker socket
      - DEBUG=1
      - DOCKER_HOST=unix:///var/run/docker.sock

      # Local AWS defaults + dummy creds (you asked to keep these)
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

      # Helpful for containers to talk to LocalStack
      - AWS_ENDPOINT_URL=http://localstack:4566
      - LOCALSTACK_HOSTNAME=localstack
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=60

    volumes:
      # Keep repo mount (so bootstrap can read /project/.env)
      - ./:/project

      # Keep your existing init hook approach (no renames)
      - ./deploy.enrollment-init.sh:/etc/localstack/init/ready.d/deploy.enrollment-init.sh

      # Needed for lambda docker runtime
      - /var/run/docker.sock:/var/run/docker.sock

      # Keep certs mount pattern (adjust left side to your actual cert folder if different)
      - ./certs:/root/certs:ro

  enrollment-writer:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: enrollment-writer

    depends_on:
      localstack:
        condition: service_healthy

    environment:
      # App
      - APP_ENV=${APP_ENV}
      - LOG_LEVEL=${LOG_LEVEL}
      - COF_SM_ENABLED=${COF_SM_ENABLED}

      # AWS -> LocalStack
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}
      - AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

      # Your code uses this to fetch secret
      - SECRET_ARN=${SECRET_ARN}

      # Keep DB vars (your app logs print these; no harm)
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}

      # CA/proxy passthrough (kept)
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - REQUESTS_CA_BUNDLE=${REQUESTS_CA_BUNDLE}
      - CURL_CA_BUNDLE=${CURL_CA_BUNDLE}
      - NODE_EXTRA_CA_CERTS=${NODE_EXTRA_CA_CERTS}

    restart: unless-stopped




////////////////////////////////





#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] Starting enrollment LocalStack init ====="

# Use the same repo-mounted env file
ENV_FILE="/project/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found (repo must be mounted to /project)."
  exit 1
fi

# Safe .env loader (avoids 'source' breaking on JSON)
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" =~ ^[[:space:]]*$ ]] && continue
  if [[ "$line" == *"="* ]]; then
    key="${line%%=*}"
    value="${line#*=}"
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

# Prefer DB_SECRET_JSON exactly like your requested format; otherwise build from DB_*
if [[ -n "${DB_SECRET_JSON:-}" ]]; then
  SECRET_JSON="${DB_SECRET_JSON}"
else
  : "${DB_HOST:?DB_HOST missing}"
  : "${DB_PORT:?DB_PORT missing}"
  : "${DB_NAME:?DB_NAME missing}"
  : "${DB_USER:?DB_USER missing}"
  : "${DB_PASSWORD:?DB_PASSWORD missing}"
  SECRET_JSON="{\"host\":\"${DB_HOST}\",\"port\":\"${DB_PORT}\",\"dbname\":\"${DB_NAME}\",\"username\":\"${DB_USER}\",\"password\":\"${DB_PASSWORD}\"}"
fi

echo "===== [bootstrap] Effective configuration ====="
echo "AWS_REGION            = ${AWS_REGION}"
echo "QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "SECRET_ARN            = ${SECRET_ARN}"
echo "DB_SECRET_JSON        = $(echo "${SECRET_JSON}" | sed -E 's/"password":"[^"]+"/"password":"***"/')"

AWSLOCAL="awslocal --region ${AWS_REGION}"

echo "===== [bootstrap] Creating S3 bucket (if needed) ====="
if ${AWSLOCAL} s3api head-bucket --bucket "${QSINK_BUCKET_NAME}" >/dev/null 2>&1; then
  echo "[bootstrap] S3 bucket exists: ${QSINK_BUCKET_NAME}"
else
  ${AWSLOCAL} s3api create-bucket --bucket "${QSINK_BUCKET_NAME}" >/dev/null
  echo "[bootstrap] S3 bucket created: ${QSINK_BUCKET_NAME}"
fi

echo "===== [bootstrap] Creating SQS queues (idempotent) ====="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null
${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null

QSINK_QUEUE_URL="$(${AWSLOCAL} sqs get-queue-url --queue-name "${QSINK_QUEUE_NAME}" --query 'QueueUrl' --output text)"
ENROLLMENT_QUEUE_URL="$(${AWSLOCAL} sqs get-queue-url --queue-name "${ENROLLMENT_QUEUE_NAME}" --query 'QueueUrl' --output text)"
echo "[bootstrap] QSINK_QUEUE_URL      = ${QSINK_QUEUE_URL}"
echo "[bootstrap] ENROLLMENT_QUEUE_URL = ${ENROLLMENT_QUEUE_URL}"

echo "===== [bootstrap] Creating/updating Secrets Manager secret ====="
if ${AWSLOCAL} secretsmanager describe-secret --secret-id "${SECRET_ARN}" >/dev/null 2>&1; then
  ${AWSLOCAL} secretsmanager put-secret-value \
    --secret-id "${SECRET_ARN}" \
    --secret-string "${SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret updated: ${SECRET_ARN}"
else
  ${AWSLOCAL} secretsmanager create-secret \
    --name "${SECRET_ARN}" \
    --secret-string "${SECRET_JSON}" >/dev/null
  echo "[bootstrap] Secret created: ${SECRET_ARN}"
fi

echo "===== [bootstrap] Init complete ====="

