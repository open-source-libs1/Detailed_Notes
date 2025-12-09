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

# Local endpoint used by scripts / Lambdas
AWS_ENDPOINT_URL=http://localhost:4566

############################################
# LocalStack Pro license
############################################
# Replace with your real token from app.localstack.cloud
LOCALSTACK_AUTH_TOKEN=ls-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

############################################
# Local resource names (must match bootstrap)
############################################
QSINK_BUCKET_NAME=qsink-bucket-local   # logical QSink bucket
QSINK_QUEUE_NAME=sqsq1                 # logical QSink queue
ENROLLMENT_QUEUE_NAME=sqsq2            # logical Enrollment queue

############################################
# OPTIONAL: Corporate proxy settings
# Fill these only if your company requires a proxy
############################################
# Example values – replace or leave empty/remove
HTTPS_PROXY=https://your.proxy.host:8443
HTTP_PROXY=http://your.proxy.host:8080
NO_PROXY=localhost,127.0.0.1,localstack,host.docker.internal





/////////////////////////////////


version: "3.9"

services:
  localstack:
    image: localstack/localstack-pro:4
    container_name: localstack

    ports:
      - "127.0.0.1:4566:4566"               # LocalStack edge
      - "127.0.0.1:4510-4559:4510-4559"     # Lambda execution ports

    environment:
      ######################################
      # LocalStack Pro activation
      ######################################
      - ACTIVATE_PRO=1
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      ######################################
      # General config
      ######################################
      - AWS_DEFAULT_REGION=us-east-1
      - DEBUG=1

      # Let LocalStack talk to the host Docker daemon (needed for Lambda containers)
      - DOCKER_HOST=unix:///var/run/docker.sock

      # Make the container think of itself as "localstack"
      - HOSTNAME_EXTERNAL=localstack
      - LOCALSTACK_HOST=localstack

      # Use your corporate Lambda base image instead of public.ecr.aws
      # (no spaces, JSON as a single line)
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # Optional: allow Lambdas longer to boot (milliseconds)
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=600000

      ######################################
      # OPTIONAL: Proxy configuration
      # Values come from .env (can be empty)
      ######################################
      - HTTPS_PROXY=${HTTPS_PROXY}
      - HTTP_PROXY=${HTTP_PROXY}
      - NO_PROXY=${NO_PROXY}

    volumes:
      # 1) Mount host Docker socket – required so LocalStack can start Lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # 2) Bootstrap script that creates S3/SQS and wires both Lambdas
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro

      # 3) Project .env so the bootstrap can read DB + queue names
      - ./.env:/project/.env:ro

      # 4) Lambda ZIPs – must appear in the container as /artifacts
      - ./.localstack/artifacts:/artifacts:ro

    restart: unless-stopped


