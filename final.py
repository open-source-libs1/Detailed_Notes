
########################################
# Aurora / DEV DB configuration
########################################
DB_HOST=my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=enrollment
DB_USER=enrollment_dev
DB_PASSWORD=super-secret-password

########################################
# Secret name used in LocalStack
# (your Python code passes this as SecretId)
########################################
SECRET_ARN=enrollment-db-local

########################################
# General app environment
########################################
APP_ENV=local
AWS_DEFAULT_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566

########################################
# Local resource names (must match bootstrap)
########################################
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

########################################
# LocalStack Pro license (not enforced)
########################################
LOCALSTACK_AUTH_TOKEN=ls-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

########################################
# Corporate proxy (mirrors working stack)
########################################
HTTP_PROXY=http://aws-proxy-dev.cloud.capitalone.com:8099
HTTPS_PROXY=http://aws-proxy-dev.cloud.capitalone.com:8099
NO_PROXY=127.0.0.1,localhost,localstack,host.docker.internal,local,169.254.169.254,.kdc.capitalone.com,.cloud.capitalone.com



/////////////////////////


version: "3.9"

services:
  ###############################################################
  # LocalStack – Pro image, “working stack” style
  ###############################################################
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack-enrollment

    ports:
      - "127.0.0.1:4566:4566"           # LocalStack HTTP Gateway
      - "127.0.0.1:4510-4559:4510-4559" # internal service port range
      - "127.0.0.1:443:443"             # HTTPS Gateway (for UI / Pro)

    extra_hosts:
      - "host.docker.internal:host-gateway"  # same trick as other team

    healthcheck:
      # basic health endpoint – same idea as other stack
      test: ["CMD", "curl", "-f", "http://localhost:4566/health"]
      interval: 90s
      timeout: 10s
      retries: 3
      start_period: 40s

    environment:
      ###########################################################
      # Core LocalStack configuration
      ###########################################################
      # NOTE: Pro image, but don't fail hard on license lookup
      - ACTIVATE_PRO=0
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      # Enable needed services (similar to other team)
      - SERVICES=cloudformation,iam,lambda,logs,secretsmanager,s3,sqs,cloudwatch

      - DEBUG=1
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}

      # Capital One wrapper flag to allow Secrets Manager
      - COF_SM_ENABLED=true

      ###########################################################
      # Proxy and CA bundle – copied pattern from other stack
      ###########################################################
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=${NO_PROXY}
      - OUTBOUND_HTTP_PROXY=${HTTP_PROXY}
      - OUTBOUND_HTTPS_PROXY=${HTTPS_PROXY}

      - REQUESTS_CA_BUNDLE=$HOME/certs/C1G2RootCA.crt
      - CURL_CA_BUNDLE=$HOME/certs/C1G2RootCA.crt
      - NODE_EXTRA_CA_CERTS=$HOME/certs/C1G2RootCA.crt

      ###########################################################
      # Lambda + Docker integration
      ###########################################################
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=600000
      - LOCALSTACK_HOSTNAME=localstack
      - LOCALSTACK_HOST=localstack

      ###########################################################
      # Dummy AWS credentials (same as other stacks)
      ###########################################################
      - AWS_ACCESS_KEY_ID=localstack
      - AWS_SECRET_ACCESS_KEY=localstack

    volumes:
      # Mount repo into /var/task (matches other project style)
      - ..:/var/task

      # Bootstrap script – name and path mirror deploy.aws-init.sh
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

  ###############################################################
  # EnrollmentWriter – ECS-style worker container
  ###############################################################
  enrollment-writer:
    build:
      context: .
      dockerfile: Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer

    depends_on:
      - localstack

    environment:
      # General app env & logging
      - APP_ENV=local
      - LOG_LEVEL=INFO

      # DB config (also stored in the secret)
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}

      # This value is passed straight into your helper as SecretId
      - SECRET_ARN=${SECRET_ARN:-enrollment-db-local}

      # Point AWS SDKs at LocalStack
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
      - AWS_ENDPOINT_URL=http://localstack:4566
      - AWS_ACCESS_KEY_ID=localstack
      - AWS_SECRET_ACCESS_KEY=localstack

      # Enrollment SQS queue URL pattern inside LocalStack
      - SOURCE_SQS_QUEUE_URL=http://sqs.${AWS_DEFAULT_REGION:-us-east-1}.localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME:-sqsq2}

    restart: unless-stopped




////////////////////////



#!/bin/bash
set -euo pipefail

echo "===== [bootstrap] Starting LocalStack enrollment deployment script... ====="

###########################################################
# 0. Pick AWS CLI wrapper (awslocal preferred)
###########################################################
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
  echo "===== [bootstrap] Using 'awslocal' CLI wrapper ====="
else
  AWSLOCAL="aws --endpoint-url=http://localstack:4566"
  echo "===== [bootstrap] 'awslocal' not found, falling back to 'aws --endpoint-url=...' ====="
fi

###########################################################
# 1. Load .env so we have DB / queue / secret config
###########################################################
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
echo "  QSink ZIP             = ${QSINK_ZIP}"
echo

###########################################################
# 2. Build DB secret payload (same style as other team)
###########################################################
# NOTE: this string must be a valid Python literal so
# your existing ast.literal_eval(...) code can parse it.
DB_SECRET_JSON="{\"host\":\"${DB_HOST}\",\"port\":\"${DB_PORT}\",\"dbname\":\"${DB_NAME}\",\"username\":\"${DB_USER}\",\"password\":\"${DB_PASSWORD}\"}"

echo "===== [bootstrap] DB secret JSON ====="
echo "  ${DB_SECRET_JSON}"
echo

###########################################################
# 3. Create S3 bucket & SQS queues (idempotent)
###########################################################
echo "===== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if needed) ====="
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] Bucket ${QSINK_BUCKET_NAME} may already exist – continuing ====="

echo "===== [bootstrap] Creating SQS queues '${QSINK_QUEUE_NAME}' and '${ENROLLMENT_QUEUE_NAME}' (if needed) ====="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] Queue ${QSINK_QUEUE_NAME} may already exist – continuing ====="

${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] Queue ${ENROLLMENT_QUEUE_NAME} may already exist – continuing ====="

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"

echo "===== [bootstrap] S3 / SQS setup complete ====="
echo "  S3 bucket        = s3://${QSINK_BUCKET_NAME}"
echo "  QSink queue ARN  = ${QSINK_QUEUE_ARN}"
echo

###########################################################
# 4. Create or update DB secret in Secrets Manager
###########################################################
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

###########################################################
# 5. Create / update QSink Forwarder Lambda from ZIP
###########################################################
if [ -f "${QSINK_ZIP}" ]; then
  echo "===== [bootstrap] Lambda ZIP found at ${QSINK_ZIP} – deploying function '${FUNCTION_NAME}' ====="

  # Environment variables passed into the Lambda (similar to other stack)
  ENV_VARS="Variables={APP_ENV=${APP_ENV:-local},AWS_DEFAULT_REGION=${AWS_REGION},QSINK_BUCKET_NAME=${QSINK_BUCKET_NAME},QSINK_QUEUE_NAME=${QSINK_QUEUE_NAME},ENROLLMENT_QUEUE_NAME=${ENROLLMENT_QUEUE_NAME},DB_SECRET_NAME=${SECRET_NAME}}"

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
    echo "  Function not found – creating new lambda..."
    ${AWSLOCAL} lambda create-function \
      --function-name "${FUNCTION_NAME}" \
      --runtime python3.12 \
      --handler "${HANDLER_PATH}" \
      --zip-file "fileb://${QSINK_ZIP}" \
      --role "${ROLE_ARN}" \
      --environment "${ENV_VARS}" >/dev/null
  fi
else
  echo "===== [bootstrap][WARN] QSink ZIP NOT found at ${QSINK_ZIP} – skipping lambda creation ====="
fi

QSINK_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"
echo
echo "===== [bootstrap] Lambda function ARN ====="
echo "  ${QSINK_LAMBDA_ARN}"
echo

###########################################################
# 6. Wire S3 PUT -> QSink lambda (like other team)
###########################################################
if [ -f "${QSINK_ZIP}" ]; then
  echo "===== [bootstrap] Wiring S3 bucket events to lambda '${FUNCTION_NAME}' ====="

  ${AWSLOCAL} lambda add-permission \
    --function-name "${FUNCTION_NAME}" \
    --statement-id s3invoke \
    --action lambda:InvokeFunction \
    --principal s3.amazonaws.com \
    --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
    echo "  Permission may already exist – continuing"

  S3_NOTIFICATION=$(cat <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "qsink-forwarder-s3-put",
      "LambdaFunctionArn": "${QSINK_LAMBDA_ARN}",
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
fi

echo
echo "===== [bootstrap] Deployment Summary ====="
echo "  DB secret name     : ${SECRET_NAME}"
echo "  QSink bucket       : ${QSINK_BUCKET_NAME}"
echo "  QSink queue        : ${QSINK_QUEUE_NAME}"
echo "  Enrollment queue   : ${ENROLLMENT_QUEUE_NAME}"
echo "  Lambda function    : ${FUNCTION_NAME}"
echo "===== [bootstrap] Deployment complete. ====="

