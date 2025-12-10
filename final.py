//// .env


########################################
# Aurora / DEV DB configuration
########################################
DB_HOST=my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=enrollment
DB_USER=enrollment_dev
DB_PASSWORD=super-secret-password

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
# LocalStack Pro license
########################################
LOCALSTACK_AUTH_TOKEN=ls-Xiga8715-JASa-rEju-LoWe-9690QEfo4dbe   # your real token

########################################
# Corporate proxy (optional)
########################################
HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=localhost,127.0.0.1,localstack,host.docker.internal





/////////////////////////////////


version: "3.8"

services:
  ########################################################
  # 1) LocalStack Pro – infra only (S3, SQS, Lambda, logs)
  ########################################################
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"

    environment:
      # --- Core LocalStack settings ---
      ACTIVATE_PRO: "1"
      SERVICES: "s3,sqs,logs,lambda,iam,cloudwatch"

      DEBUG: "1"
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"

      # Pro license
      LOCALSTACK_AUTH_TOKEN: "${LOCALSTACK_AUTH_TOKEN}"

      # --- Lambda + Docker integration ---
      DOCKER_HOST: "unix:///var/run/docker.sock"
      LAMBDA_RUNTIME_IMAGE_MAPPING: >
        {"python3.12": "artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}
      LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT: "600000"
      HOSTNAME_EXTERNAL: "localstack"
      LOCALSTACK_HOST: "localstack"

      # --- Proxy / TLS certs inside the container ---
      HTTP_PROXY: "${HTTP_PROXY}"
      HTTPS_PROXY: "${HTTPS_PROXY}"
      NO_PROXY: "${NO_PROXY:-localhost,127.0.0.1,localstack,host.docker.internal}"

      OUTBOUND_HTTP_PROXY: "${HTTP_PROXY}"
      OUTBOUND_HTTPS_PROXY: "${HTTPS_PROXY}"

      # Cert bundle *inside* container – we mount host ~/certs -> /root/certs
      REQUESTS_CA_BUNDLE: "/root/certs/C1G2RootCA.crt"
      CURL_CA_BUNDLE: "/root/certs/C1G2RootCA.crt"
      NODE_EXTRA_CA_CERTS: "/root/certs/C1G2RootCA.crt"

    volumes:
      # Host certs -> container /root/certs
      - "${HOME}/certs:/root/certs:ro"

      # LocalStack state
      - "./.volume:/var/lib/localstack"

      # Host Docker socket (required for Lambda containers)
      - "/var/run/docker.sock:/var/run/docker.sock"

      # Bootstrap script (creates S3/SQS + QSink Lambda wiring)
      - "./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro"

      # .env so bootstrap can read DB + queue names
      - "./.env:/project/.env:ro"

      # Lambda ZIP artifacts for QSink forwarder
      - "./.localstack/artifacts:/artifacts:ro"

    restart: unless-stopped

  ########################################################
  # 2) EnrollmentWriter ECS-style worker (local dev)
  ########################################################
  enrollment-writer:
    image: python:3.12
    container_name: enrollment-writer
    depends_on:
      - localstack
    working_dir: /app

    # Mount your actual code into the container
    volumes:
      # Adjust path if your package dir is different
      - "./enrollment_writer:/app"

    environment:
      # AWS / LocalStack
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"
      AWS_ENDPOINT_URL: "http://localstack:4566"
      AWS_ACCESS_KEY_ID: "localstack"
      AWS_SECRET_ACCESS_KEY: "localstack"

      # SQS Q2 URL – what main.py expects as SOURCE_SQS_QUEUE_URL
      # LocalStack pattern: http://localstack:4566/000000000000/<queue-name>
      SOURCE_SQS_QUEUE_URL: "http://localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME}"

      # Logging
      LOG_LEVEL: "DEBUG"

      # DB config
      DB_HOST: "${DB_HOST}"
      DB_PORT: "${DB_PORT}"
      DB_NAME: "${DB_NAME}"
      DB_USER: "${DB_USER}"
      DB_PASSWORD: "${DB_PASSWORD}"

    # Run the same entrypoint that ECS runs:
    # from your screenshots: app/main.py defines if __name__ == '__main__': process()
    command: ["python", "app/main.py"]
    restart: unless-stopped





//////////////////


#!/usr/bin/env bash
set -euo pipefail

echo "===== [bootstrap] LocalStack enrollment stack bootstrap starting... ====="
echo ""

########################################
# 0) Choose AWS CLI wrapper
########################################
if command -v awslocal >/dev/null 2>&1; then
  AWSLOCAL="awslocal"
  echo "===== [bootstrap] Using 'awslocal' CLI wrapper ====="
else
  AWSLOCAL="aws --endpoint-url=http://localhost:4566"
  echo "===== [bootstrap] 'awslocal' not found, using 'aws --endpoint-url=...' ====="
fi

########################################
# 1) Load .env from /project
########################################
ENV_FILE="/project/.env"

if [ -f "$ENV_FILE" ]; then
  echo "===== [bootstrap] Loading environment from ${ENV_FILE} ====="
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
  echo ""
else
  echo "===== [bootstrap][WARN] .env file not found at ${ENV_FILE} ====="
  echo "===== [bootstrap][WARN] Using default values for region/bucket/queues ====="
fi

########################################
# 2) Core settings
########################################
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
echo ""

########################################
# 3) QSink Lambda ZIP
########################################
QSINK_ZIP="${ARTIFACT_DIR}/qsink-referrals-enrollment.zip"

echo "===== [bootstrap] Checking QSink Lambda artifact ====="
echo "  QSink ZIP = ${QSINK_ZIP}"
echo ""

QSINK_ZIP_OK=true
if [ ! -f "${QSINK_ZIP}" ]; then
  echo "===== [bootstrap][ERROR] QSink ZIP not found at ${QSINK_ZIP} ====="
  echo "===== [bootstrap][HINT] On your host, run: ./build_lambdas.sh ====="
  QSINK_ZIP_OK=false
fi

########################################
# 4) Create S3 bucket + both SQS queues
########################################
echo "===== [bootstrap] Creating S3 bucket '${QSINK_BUCKET_NAME}' (if not exists) ====="
${AWSLOCAL} s3 mb "s3://${QSINK_BUCKET_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] S3 bucket may already exist, continuing ====="

echo "===== [bootstrap] Creating SQS queues (if not exists) ====="
${AWSLOCAL} sqs create-queue --queue-name "${QSINK_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] SQS ${QSINK_QUEUE_NAME} may already exist, continuing ====="
${AWSLOCAL} sqs create-queue --queue-name "${ENROLLMENT_QUEUE_NAME}" >/dev/null 2>&1 || \
  echo "===== [bootstrap] SQS ${ENROLLMENT_QUEUE_NAME} may already exist, continuing ====="

QSINK_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${QSINK_QUEUE_NAME}"
ENROLLMENT_QUEUE_ARN="arn:aws:sqs:${AWS_REGION}:${ACCOUNT_ID}:${ENROLLMENT_QUEUE_NAME}"

echo "===== [bootstrap] Created / verified resources ====="
echo "  S3 bucket             = s3://${QSINK_BUCKET_NAME}"
echo "  QSink queue ARN       = ${QSINK_QUEUE_ARN}"
echo "  Enrollment queue ARN  = ${ENROLLMENT_QUEUE_ARN}"
echo ""

########################################
# 5) Shared env for QSink Lambda
########################################
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
echo ""

########################################
# 6) Create QSink Forwarder Lambda
########################################
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
  >/dev/null 2>&1 || echo "===== [bootstrap] Lambda qsink-forwarder-lambda may already exist, skipping create ====="
else
  echo "===== [bootstrap][WARN] Skipping qsink-forwarder-lambda (ZIP missing) ====="
fi

QSINK_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:qsink-forwarder-lambda"

########################################
# 7) Wire SQS Q1 -> QSink Lambda
########################################
echo "===== [bootstrap] Wiring SQS '${QSINK_QUEUE_NAME}' -> QSink Lambda ====="

${AWSLOCAL} lambda create-event-source-mapping \
  --function-name qsink-forwarder-lambda \
  --event-source-arn "${QSINK_QUEUE_ARN}" \
  --batch-size 1 \
>/dev/null 2>&1 || echo "===== [bootstrap] Mapping (QSink queue -> QSink Lambda) may already exist ====="

########################################
# 8) Wire S3 PUT -> QSink Lambda
########################################
echo "===== [bootstrap] Wiring S3 PUT -> QSink Lambda ====="

${AWSLOCAL} lambda add-permission \
  --function-name qsink-forwarder-lambda \
  --statement-id s3invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${QSINK_BUCKET_NAME}" \
>/dev/null 2>&1 || echo "===== [bootstrap] Lambda permission for S3 may already exist ====="

S3_NOTIFICATION=$(cat <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "qsink-forwarder-s3-put",
      "LambdaFunctionArn": "${QSINK_LAMBDA_ARN}",
      "Events": [ "s3:ObjectCreated:Put" ]
    }
  ]
}
EOF
)

${AWSLOCAL} s3api put-bucket-notification-configuration \
  --bucket "${QSINK_BUCKET_NAME}" \
  --notification-configuration "${S3_NOTIFICATION}" \
>/dev/null 2>&1 || echo "===== [bootstrap] Failed to set S3 notification (may already exist) ====="

echo ""
echo "===== [bootstrap] LocalStack enrollment bootstrap finished successfully ====="
echo ""





