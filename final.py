# EnrollmentWriter + QSink LocalStack Environment

This repo provides an end-to-end local environment for testing the **EnrollmentWriter** service together with the **QSink Forwarder Lambda** using **LocalStack Pro**.

---

## Architecture Overview

Local flow:

1. **S3 bucket** `qsink-bucket-local` receives input objects.
2. **QSink Forwarder Lambda** is triggered by S3 PUT events and publishes to:
   - **SQS Q1** (`sqsq1`) and
   - **SQS Q2** (`sqsq2`).
3. **EnrollmentWriter** runs in its own Docker container, polls **SQS Q2**, and writes results into the configured **Postgres / Aurora** database.

---

## Prerequisites

- Docker Desktop with Docker Compose v2.
- LocalStack Pro account and **AUTH token**.
- AWS CLI v2 installed on the host.
- Network access from your laptop to the target DB (local Postgres or DEV Aurora).
- Corporate CA certificate and proxy configuration (e.g. `C1G2RootCA.crt` under `~/certs`).
- Python toolchain required by `build_lambdas.sh` (usually `pipenv` or system Python).

---

## Important Files

- `.env` – single source of truth for LocalStack, DB, queues, secret name, CA bundles and proxies.
- `docker-compose.yml` – brings up **LocalStack Pro** + **EnrollmentWriter**.
- `Dockerfile` – EnrollmentWriter container image.
- `build_lambdas.sh` – builds the QSink lambda ZIP into `.localstack/artifacts/`.
- `localstack_bootstrap.sh` – LocalStack init script that creates:
  - S3 bucket, SQS queues, Secrets Manager secret, QSink Lambda, and S3→Lambda wiring.
- `enrollment_writer/` – EnrollmentWriter app code.


## Build 
./build_lambdas.sh

## Run
docker compose up --build

## EnrollmentWriter DB connection + message handling
docker compose logs -f enrollment-writer


## Run
docker compose up --build             

## Tests
export ENDPOINT=http://localhost:4566

# Get Enrollment queue URL (sqsq2)
ENR_URL=$(aws --endpoint-url="$ENDPOINT" sqs get-queue-url \
  --queue-name sqsq2 \
  --query 'QueueUrl' \
  --output text)

echo "Enrollment queue URL: $ENR_URL"

# Send message using JSON from file
aws --endpoint-url="$ENDPOINT" sqs send-message \
  --queue-url "$ENR_URL" \
  --message-body "file://tests/local/enrollment-test.json"

