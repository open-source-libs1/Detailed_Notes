############################################
# Aurora / DEV DB configuration
############################################
DB_HOST=my-dev-aurora.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=enrollment
DB_USER=enrollment_dev
DB_PASSWORD=super-secret-password

############################################
# General app environment
############################################
APP_ENV=local
AWS_DEFAULT_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566

############################################
# Local resource names
############################################
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

############################################
# OPTIONAL Proxy (only if required)
############################################
HTTPS_PROXY=
HTTP_PROXY=
NO_PROXY=localhost,127.0.0.1,localstack






//////////////////////////


version: "3.9"

services:
  localstack:
    image: localstack/localstack:3.6
    container_name: localstack

    ports:
      - "4566:4566"
      - "4510-4559:4510-4559"

    environment:
      - SERVICES=s3,sqs,lambda
      - DEBUG=1
      - AWS_DEFAULT_REGION=us-east-1

      # Important: allow LocalStack to start Lambda containers
      - DOCKER_HOST=unix:///var/run/docker.sock

      # Where the bootstrap script reads .env
      - LOCALSTACK_HOST=localstack
      - HOSTNAME_EXTERNAL=localstack

    volumes:
      # Allow LocalStack to start Lambda docker containers
      - /var/run/docker.sock:/var/run/docker.sock

      # Bootstrap script for S3/SQS/Lambda setup
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro

      # Pass .env from host → container so bootstrap can read DB + queue names
      - ./.env:/project/.env:ro

      # Lambda ZIPs (required if bootstrap deploys Lambda functions)
      - ./.localstack/artifacts:/artifacts:ro

    restart: unless-stopped



