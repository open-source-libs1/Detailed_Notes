/////////////////////////////////


version: "3.9"

services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"

    environment:
      ########################################
      # Core LocalStack settings
      ########################################
      - ACTIVATE_PRO=1
      # we need S3 + SQS + Lambda + logging
      - SERVICES=s3,sqs,logs,lambda,iam,cloudwatch
      - DEBUG=1
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}

      # License token comes from .env
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      ########################################
      # Lambda + Docker integration
      ########################################
      # let LocalStack talk to host Docker to start Lambda containers
      - DOCKER_HOST=unix:///var/run/docker.sock

      # map AWS python3.12 runtime to your corporate Lambda base image
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # optional: give Lambda a bit longer to start (ms)
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=600000

      # make the container think its hostname is "localstack"
      - HOSTNAME_EXTERNAL=localstack
      - LOCALSTACK_HOST=localstack

      ########################################
      # Proxy + TLS (so Pro license calls work)
      ########################################
      # use your corp proxy values from ~/.env
      - OUTBOUND_HTTP_PROXY=${HTTP_PROXY}
      - OUTBOUND_HTTPS_PROXY=${HTTP_PROXY}

      # inside the container we mount the cert to /root/certs
      - REQUESTS_CA_BUNDLE=/root/certs/C1G2RootCA.crt
      - CURL_CA_BUNDLE=/root/certs/C1G2RootCA.crt
      - NODE_EXTRA_CA_CERTS=/root/certs/C1G2RootCA.crt

      ########################################
      # Dummy AWS creds (required by some SDKs)
      ########################################
      - AWS_ACCESS_KEY_ID=localstack
      - AWS_SECRET_ACCESS_KEY=localstack

    volumes:
      # C1 root cert: host ~/certs -> container /root/certs
      - ${HOME}/certs:/root/certs:ro

      # LocalStack state (optional but nice so it can cache things)
      - ./.volume:/var/lib/localstack

      # Host Docker socket (needed to start Lambda containers)
      - /var/run/docker.sock:/var/run/docker.sock

      # Bootstrap script (runs when LocalStack is "ready")
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro

      # .env inside container at /project/.env so bootstrap can read it
      - ./.env:/project/.env:ro

      # Lambda ZIP artifacts from your repo
      - ./.localstack/artifacts:/artifacts:ro

    restart: unless-stopped

  ####################################################################
  # EnrollmentWriter “ECS style” worker container
  ####################################################################
  enrollment-writer:
    build:
      context: .
      dockerfile: Dockerfile
    image: enrollment-writer-local:latest
    container_name: enrollment-writer

    depends_on:
      - localstack

    environment:
      # general app env
      - APP_ENV=local
      - LOG_LEVEL=INFO

      # DB config comes straight from your .env
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}

      # tell the worker to talk to LocalStack
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
      - AWS_ENDPOINT_URL=http://localstack:4566
      - AWS_ACCESS_KEY_ID=localstack
      - AWS_SECRET_ACCESS_KEY=localstack

      # Enrollment queue URL (Q2) inside LocalStack
      # pattern matches what LocalStack creates:
      #   http://sqs.<region>.localstack:4566/000000000000/<queue-name>
      - SOURCE_SQS_QUEUE_URL=http://sqs.${AWS_DEFAULT_REGION:-us-east-1}.localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME:-sqsq2}

    # no ports needed – it’s a background worker
    restart: unless-stopped





//////////////////

#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] LocalStack enrollment stack bootstrap starting... ====="
echo

###############################################
# 0) Choose AWS CLI wrapper (awslocal or aws)
###############################################
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
  echo "===== [bootstrap] Using 'awslocal' CLI wrapper ====="
else
  AWSLOCAL="aws --endpoint-url=http://localstack:4566"
  echo "===== [bootstrap] 'awslocal' not found, using 'aws --endpoint-url=...' ====="
fi

###############################################
# 1) Load .env from /project/.env
###############################################
ENV_FILE="/project/.env"

if [ -f "$ENV_FILE" ]; then
  echo "===== [bootstrap] Loading environment from ${ENV_FILE} ====="
  # automatically export everything from .env
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a

  echo "===== [bootstrap] Environment after loading .env (key vars) ====="
  echo "  APP_ENV               = ${APP_ENV:-<unset>}"
  echo "  AWS_DEFAULT_REGION    = ${AWS_DEFAULT_REGION:-<unset>}"
  echo "  QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME:-<unset>}"
  echo "  QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME:-<unset>}"
  echo "  ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME:-<unset>}"
  echo "  DB_HOST               = ${DB_HOST:-<unset>}"
  echo "  DB_NAME               = ${DB_NAME:-<unset>}"
else
  echo "===== [bootstrap][WARN] .env file not found at ${ENV_FILE} ====="
  echo "===== [bootstrap][WARN] Using default values for region/bucket/queues ====="
fi
echo

AWS_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"

QSINK_BUCKET_NAME="${QSINK_BUCKET_NAME:-qsink-bucket-local}"
QSINK_QUEUE_NAME="${QSINK_QUEUE_NAME:-sqsq1}"
ENROLLMENT_QUEUE_NAME="${ENROLLMENT_QUEUE_NAME:-sqsq2}"

ARTIFACT_DIR="/artifacts"

echo "===== [bootstrap] Effective configuration ====="
echo "  AWS_REGION            = ${AWS_REGION}"
echo "  ACCOUNT_ID            = ${ACCOUNT_ID}"
echo "  QSINK_BUCKET_NAME     = ${QSINK_BUCKET_NAME}"
echo "  QSINK_QUEUE_NAME      = ${QSINK_QUEUE_NAME}"
echo "  ENROLLMENT_QUEUE_NAME = ${ENROLLMENT_QUEUE_NAME}"
echo "  ARTIFACT_DIR          = ${ARTIFACT_DIR}"
echo

###############################################
# 2) Verify Lambda ZIP artifacts exist
###############################################
QSINK_ZIP="${ARTIFACT_DIR}/qsink-referrals-enrollment.zip"

echo "===== [bootstrap] Checking Lambda artifacts ====="
echo "  QSink ZIP             = ${QSINK_ZIP}"

QSINK_ZIP_OK=true
if [ ! -f "${QSINK_ZIP}" ]; then
  echo "===== [bootstrap][ERROR] QSink ZIP not found at ${QSINK_ZIP} ====="
  echo "===== [bootstrap][HINT ] On your host, run: ./build_lambdas.sh ====="
  QSINK_ZIP_OK=false
fi
echo

###############################################
# 3) Create S3 / SQS resources (idempotent)
###############################################
echo "===== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if not exists) ====="
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] S3 bucket ${QSINK_BUCKET_NAME} may already exist, continuing ====="

echo "===== [bootstrap] Creating SQS queues (if not exists) ====="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] SQS queue ${QSINK_QUEUE_NAME} may already exist, continuing ====="

${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] SQS queue ${ENROLLMENT_QUEUE_NAME} may already exist, continuing ====="

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"

echo "===== [bootstrap] Created / verified resources ====="
echo "  S3 bucket        = s3://${QSINK_BUCKET_NAME}"
echo "  QSink queue ARN  = ${QSINK_QUEUE_ARN}"
echo

###############################################
# 4) Shared Lambda environment JSON
###############################################
echo "===== [bootstrap] Building shared Lambda environment JSON ====="

COMMON_ENV_JSON=$(cat <<EOF
{
  "Variables": {
    "APP_ENV": "${APP_ENV:-local}",
    "AWS_DEFAULT_REGION": "${AWS_REGION}",
    "AWS_ENDPOINT_URL": "http://localstack:4566",
    "QSINK_BUCKET_NAME": "${QSINK_BUCKET_NAME}",
    "QSINK_QUEUE_NAME": "${QSINK_QUEUE_NAME}",
    "ENROLLMENT_QUEUE_NAME": "${ENROLLMENT_QUEUE_NAME}",
    "DB_HOST": "${DB_HOST:-}",
    "DB_PORT": "${DB_PORT:-}",
    "DB_NAME": "${DB_NAME:-}",
    "DB_USER": "${DB_USER:-}",
    "DB_PASSWORD": "${DB_PASSWORD:-}"
  }
}
EOF
)

echo "===== [bootstrap] Shared Lambda environment JSON is: ====="
echo "${COMMON_ENV_JSON}"
echo

###############################################
# 5) Create QSink Forwarder Lambda (only one Lambda)
###############################################
QSINK_HANDLER="handler.lambda_handler"

if [ "${QSINK_ZIP_OK}" = true ]; then
  echo "===== [bootstrap] Creating / updating 'qsink-forwarder-lambda' ====="
  ${AWSLOCAL} lambda create-function \
    --function-name qsink-forwarder-lambda \
    --runtime python3.12 \
    --handler "${QSINK_HANDLER}" \
    --zip-file "fileb://${QSINK_ZIP}" \
    --role "arn:aws:iam::${ACCOUNT_ID}:role/lambda-role" \
    --environment "${COMMON_ENV_JSON}" \
    >/dev/null 2>&1 || \
    echo "===== [bootstrap] Lambda qsink-forwarder-lambda may already exist, skipping create ====="
else
  echo "===== [bootstrap][WARN] Skipping qsink-forwarder-lambda (ZIP missing) ====="
fi

QSINK_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:qsink-forwarder-lambda"

###############################################
# 6) Wire S3 PUT -> QSink Forwarder Lambda
###############################################
echo "===== [bootstrap] Wiring S3 PUT -> QSink Forwarder Lambda ====="

${AWSLOCAL} lambda add-permission \
  --function-name qsink-forwarder-lambda \
  --statement-id s3invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" \
  >/dev/null 2>&1 || \
  echo "===== [bootstrap] Lambda permission for S3 may already exist ====="

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
  --notification-configuration "${S3_NOTIFICATION}" \
  >/dev/null 2>&1 || \
  echo "===== [bootstrap] Failed to set S3 notification (may already exist) ====="

echo
echo "===== [bootstrap] LocalStack enrollment bootstrap finished successfully ====="
echo
