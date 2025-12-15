########################################
# LocalStack Pro
########################################
ACTIVATE_PRO=1
LOCALSTACK_AUTH_TOKEN=

########################################
# AWS / region
########################################
AWS_DEFAULT_REGION=us-east-1
AWS_REGION=us-east-1

# Host uses localhost; containers talk to "localstack" hostname
AWS_ENDPOINT_URL=http://localstack:4566

# Dummy AWS creds for LocalStack
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack

########################################
# App toggles
########################################
APP_ENV=local
LOG_LEVEL=INFO
COF_SM_ENABLED=true

########################################
# Local resource names (must match bootstrap)
########################################
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

# DB secret name used in LocalStack (what your app calls SECRET_ARN)
SECRET_ARN=enrollment-db-local

########################################
# DB connection details (DEV Aurora)
########################################
DB_HOST=my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=enrollment
DB_USER=enrollment_dev
DB_PASSWORD=super-secret-password

# Optional: explicit secret payload (bootstrap will use this if set)
# NOTE: must be a valid Python literal string for ast.literal_eval(...)
DB_SECRET_JSON={"host":"my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com","port":"5432","dbname":"enrollment","username":"enrollment_dev","password":"super-secret-password"}

########################################
# Corporate CA bundles
########################################
REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt




///////////////////////////



version: "3.9"

services:
  ########################################
  # LocalStack Pro 4.8
  ########################################
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment

    ports:
      - "127.0.0.1:4566:4566"               # LocalStack HTTP Gateway
      - "127.0.0.1:4510-4559:4510-4559"     # internal service port range
      - "127.0.0.1:443:443"                 # HTTPS Gateway (for UI / Pro)

    extra_hosts:
      - "host.docker.internal:host-gateway" # Docker Desktop compatibility

    healthcheck:
      test: [ "CMD", "curl", "-sf", "http://localhost:4566/_localstack/health" ]
      interval: 20s
      timeout: 10s
      retries: 15
      start_period: 30s

    environment:
      ########################################
      # Pro activation
      ########################################
      - ACTIVATE_PRO=${ACTIVATE_PRO:-1}
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      ########################################
      # Enable needed services
      ########################################
      - SERVICES=cloudformation,iam,lambda,logs,secretsmanager,s3,sqs,cloudwatch
      - DEBUG=1
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}

      ########################################
      # Proxy + CA bundle
      ########################################
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - OUTBOUND_HTTP_PROXY=${HTTP_PROXY}
      - OUTBOUND_HTTPS_PROXY=${HTTPS_PROXY}

      - REQUESTS_CA_BUNDLE=${REQUESTS_CA_BUNDLE}
      - CURL_CA_BUNDLE=${CURL_CA_BUNDLE}
      - NODE_EXTRA_CA_CERTS=${NODE_EXTRA_CA_CERTS}

      ########################################
      # Lambda + Docker integration
      ########################################
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=600000
      - LOCALSTACK_HOSTNAME=localstack
      - LOCALSTACK_HOST=localstack

      ########################################
      # Dummy AWS credentials (same as other stacks)
      ########################################
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

    volumes:
      # Mount repo into /var/task (matches other project style)
      - ./:/var/task

      # Bootstrap script – called deploy.enrollment-init.sh inside container
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/deploy.enrollment-init.sh:ro

      # Docker socket so LocalStack can spin up Lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # Corporate root CA bundle (same as other team)
      - $HOME/certs:$HOME/certs:ro

      # LocalStack internal data directory
      - ./.volume:/var/lib/localstack

      # .env for bootstrap to read DB / queues / SECRET_ARN
      - ./.env:/project/.env:ro

      # Lambda ZIP artifacts (built by your existing build script)
      - ./.localstack/artifacts:/artifacts:ro

    restart: unless-stopped

  ########################################
  # EnrollmentWriter – ECS-style worker container
  ########################################
  enrollment-writer:
    build:
      context: .
      dockerfile: Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer

    depends_on:
      localstack:
        condition: service_healthy

    environment:
      ########################################
      # App
      ########################################
      - APP_ENV=${APP_ENV}
      - LOG_LEVEL=${LOG_LEVEL}
      - COF_SM_ENABLED=${COF_SM_ENABLED}

      ########################################
      # AWS -> LocalStack
      ########################################
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - AWS_REGION=${AWS_REGION}
      - AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

      ########################################
      # Your code uses this to fetch secret
      ########################################
      - SECRET_ARN=${SECRET_ARN}

      ########################################
      # DB vars (your app also logs these – harmless to keep)
      ########################################
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}

      ########################################
      # CA/proxy passthrough (kept)
      ########################################
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - REQUESTS_CA_BUNDLE=${REQUESTS_CA_BUNDLE}
      - CURL_CA_BUNDLE=${CURL_CA_BUNDLE}
      - NODE_EXTRA_CA_CERTS=${NODE_EXTRA_CA_CERTS}

      ########################################
      # Enrollment SQS queue URL pattern inside LocalStack
      ########################################
      - SOURCE_SQS_QUEUE_URL=http://sqs.${AWS_DEFAULT_REGION:-us-east-1}.localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME:-sqsq2}

    restart: unless-stopped




///////////////////////////////////////




#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] Starting LocalStack enrollment deployment script... ====="

########################################
# 0. Pick AWS CLI wrapper (awslocal preferred)
########################################
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
  echo "===== [bootstrap] Using 'awslocal' CLI wrapper ====="
else
  AWSLOCAL="aws --endpoint-url=http://localstack:4566"
  echo "===== [bootstrap] 'awslocal' not found, falling back to 'aws --endpoint-url=...' ====="
fi

########################################
# 1. Load .env so we have DB / queue / secret config
########################################
ENV_FILE="/project/.env"

if [ -f "$ENV_FILE" ]; then
  echo "===== [bootstrap] Loading environment from ${ENV_FILE} ====="
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
else
  echo "===== [bootstrap][WARN] .env not found at ${ENV_FILE} – using defaults ====="
fi

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

SECRET_NAME="${SECRET_ARN:-enrollment-db-local}"

ARTIFACT_DIR="/artifacts"
QSINK_ZIP="${ARTIFACT_DIR}/qsink-referrals-enrollment.zip"

FUNCTION_NAME="qsink-forwarder-lambda"
HANDLER_PATH="handler.lambda_handler"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/lambda-role"

echo "===== [bootstrap] Effective configuration ====="
echo "  AWS_REGION            = ${AWS_REGION}"
echo "  QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "  QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "  ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "  SECRET_NAME           = ${SECRET_NAME}"
echo "  ARTIFACT_DIR          = ${ARTIFACT_DIR}"
echo "  QSINK_ZIP             = ${QSINK_ZIP}"
echo "  FUNCTION_NAME         = ${FUNCTION_NAME}"
echo

########################################
# 2. Build DB secret payload
#    (if DB_SECRET_JSON is already set in .env, we reuse it)
########################################
if [ -z "${DB_SECRET_JSON:-}" ]; then
  DB_SECRET_JSON="{\"host\":\"${DB_HOST}\",\"port\":\"${DB_PORT}\",\"dbname\":\"${DB_NAME}\",\"username\":\"${DB_USER}\",\"password\":\"${DB_PASSWORD}\"}"
fi

echo "===== [bootstrap] DB secret JSON ====="
echo "${DB_SECRET_JSON}" | sed -E 's/"password":"[^"]+"/"password":"***"/'
echo

########################################
# 3. Create S3 bucket & SQS queues (idempotent)
########################################
echo "===== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if needed) ====="
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "[bootstrap] Bucket ${QSINK_BUCKET_NAME} may already exist, continuing"

echo "===== [bootstrap] Creating SQS queues '${QSINK_QUEUE_NAME}' and '${ENROLLMENT_QUEUE_NAME}' (if needed) ====="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "[bootstrap] Queue ${QSINK_QUEUE_NAME} may already exist, continuing"

${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "[bootstrap] Queue ${ENROLLMENT_QUEUE_NAME} may already exist, continuing"

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"

echo "===== [bootstrap] S3 / SQS setup complete ====="
echo "  S3 bucket        = s3://${QSINK_BUCKET_NAME}"
echo "  QSink queue ARN  = ${QSINK_QUEUE_ARN}"
echo

########################################
# 4. Create / update DB secret in Secrets Manager
########################################
echo "===== [bootstrap] Creating/updating Secrets Manager secret '${SECRET_NAME}' ====="
if ${AWSLOCAL} secretsmanager describe-secret --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
  echo "  Secret exists – updating value..."
  ${AWSLOCAL} secretsmanager put-secret-value \
    --secret-id "${SECRET_NAME}" \
    --secret-string "${DB_SECRET_JSON}" >/dev/null
else
  echo "  Secret not found – creating..."
  ${AWSLOCAL} secretsmanager create-secret \
    --name "${SECRET_NAME}" \
    --secret-string "${DB_SECRET_JSON}" >/dev/null
fi

echo "===== [bootstrap] DB secret ready in Secrets Manager ====="
echo

########################################
# 5. Create / update QSink Forwarder Lambda from ZIP
########################################
if [ -f "${QSINK_ZIP}" ]; then
  echo "===== [bootstrap] Lambda ZIP found at ${QSINK_ZIP} – deploying function '${FUNCTION_NAME}' ====="

  # Environment variables passed into the Lambda
  ENV_VARS="Variables={APP_ENV=${APP_ENV:-local},AWS_DEFAULT_REGION=${AWS_REGION},QSINK_BUCKET_NAME=${QSINK_BUCKET_NAME},QSINK_QUEUE_NAME=${QSINK_QUEUE_NAME},ENROLLMENT_QUEUE_NAME=${ENROLLMENT_QUEUE_NAME},DB_SECRET_ARN=${SECRET_NAME}}"

  if ${AWSLOCAL} lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
    echo "  Function exists – updating code and configuration..."
    ${AWSLOCAL} lambda update-function-code \
      --function-name "${FUNCTION_NAME}" \
      --zip-file "fileb://${QSINK_ZIP}" >/dev/null

    ${AWSLOCAL} lambda update-function-configuration \
      --function-name "${FUNCTION_NAME}" \
      --handler "${HANDLER_PATH}" \
      --runtime python3.12 \
      --role "${ROLE_ARN}" \
      --environment "${ENV_VARS}" >/dev/null
  else
    echo "  Function not found – creating new function..."
    ${AWSLOCAL} lambda create-function \
      --function-name "${FUNCTION_NAME}" \
      --runtime python3.12 \
      --handler "${HANDLER_PATH}" \
      --role "${ROLE_ARN}" \
      --zip-file "fileb://${QSINK_ZIP}" \
      --environment "${ENV_VARS}" >/dev/null
  fi
else
  echo "===== [bootstrap][WARN] Lambda ZIP NOT found at ${QSINK_ZIP} – run build_lambdas.sh first ====="
fi

########################################
# 6. Wire S3 PUT -> QSink Forwarder Lambda (same as before)
########################################
echo "===== [bootstrap] Wiring S3 PUT -> QSink Forwarder Lambda ====="

${AWSLOCAL} lambda add-permission \
  --function-name "${FUNCTION_NAME}" \
  --statement-id s3invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "  Lambda permission for S3 may already exist"

S3_NOTIFICATION=$(cat <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "qsink-forwarder-s3-put",
      "LambdaFunctionArn": "arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}",
      "Events": ["s3:ObjectCreated:Put"]
    }
  ]
}
EOF
)

${AWSLOCAL} s3api put-bucket-notification-configuration \
  --bucket "${QSINK_BUCKET_NAME}" \
  --notification-configuration "${S3_NOTIFICATION}" >/dev/null 2>&1 || \
  echo "  Failed to set S3 notification (may already exist)"

echo
echo "===== [bootstrap] LocalStack enrollment bootstrap finished successfully ====="

