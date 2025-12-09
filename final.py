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
# Local resource names (match bootstrap)
############################################
QSINK_BUCKET_NAME=qsink-bucket-local
QSINK_QUEUE_NAME=sqsq1
ENROLLMENT_QUEUE_NAME=sqsq2

############################################
# LocalStack Pro license
############################################
# Paste the token from app.localstack.cloud here:
LOCALSTACK_AUTH_TOKEN=ls-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

############################################
# Corporate proxy (for license + pulling images)
# Fill these in with your real proxy URLs/ports.
# If you don't need a proxy, leave them blank.
############################################
HTTPS_PROXY=http://your-proxy-host:port
HTTP_PROXY=http://your-proxy-host:port
NO_PROXY=localhost,127.0.0.1,localstack,host.docker.internal




///////////////////////



version: "3.9"

services:
  localstack:
    image: localstack/localstack-pro:4.11.1  # or your corp-mirrored Pro image
    container_name: localstack

    # Load all key/value pairs from .env into the container environment
    env_file:
      - .env

    ports:
      - "4566:4566"
      - "4510-4559:4510-4559"

    environment:
      ########################################
      # Core LocalStack settings
      ########################################

      # Keep Pro enabled (we’re explicitly using Pro)
      - ACTIVATE_PRO=1

      # AWS services we need
      - SERVICES=s3,sqs,lambda,iam,cloudwatch

      # Debug + default region (value comes from .env, falls back to us-east-1)
      - DEBUG=1
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}

      # License token (comes from .env)
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}

      ########################################
      # Lambda + Docker integration
      ########################################

      # Let LocalStack talk to host Docker daemon to start Lambda containers
      - DOCKER_HOST=unix:///var/run/docker.sock

      # Use your corporate Lambda Python 3.12 runtime image
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # Optional: allow longer startup for Lambdas (ms)
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=600000

      # Make the container think its name is "localstack"
      - HOSTNAME_EXTERNAL=localstack
      - LOCALSTACK_HOST=localstack

      ########################################
      # Proxy settings for inside the container
      ########################################
      # These values come directly from .env
      - HTTPS_PROXY=${HTTPS_PROXY}
      - HTTP_PROXY=${HTTP_PROXY}
      - NO_PROXY=${NO_PROXY}

    volumes:
      ########################################
      # 1) Mount host Docker socket (required for Lambda containers)
      ########################################
      - /var/run/docker.sock:/var/run/docker.sock

      ########################################
      # 2) Bootstrap script (creates S3/SQS/Lambdas)
      ########################################
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro

      ########################################
      # 3) .env file inside container at /project/.env
      #    (so bootstrap can source DB + queue names)
      ########################################
      - ./.env:/project/.env:ro

      ########################################
      # 4) Lambda ZIP artifacts for deployment
      ########################################
      - ./.localstack/artifacts:/artifacts:ro

    restart: unless-stopped


