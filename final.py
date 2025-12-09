version: "3.8"

services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4
    container_name: localstack

    ports:
      # LocalStack gateway + service port range
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"

    environment:
      # We’re using the Pro image but running in “community mode”
      - ACTIVATE_PRO=0

      # Services we actually need
      - SERVICES=s3,sqs,iam,lambda,cloudwatch,logs

      # Region + debug
      - AWS_DEFAULT_REGION=us-east-1
      - DEBUG=1

      # *** IMPORTANT: let LocalStack talk to the HOST Docker daemon ***
      - DOCKER_HOST=unix:///var/run/docker.sock

      # Use your corporate Lambda base image instead of public.ecr.aws
      # (no spaces, JSON as a single line)
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # Make the container think of itself as “localstack”
      - HOSTNAME_EXTERNAL=localstack
      - LOCALSTACK_HOST=localstack

      # Optional: slightly longer Lambda startup timeout (ms)
      - LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=600000

    volumes:
      # 1) Mount host Docker socket -> required for Lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # 2) Bootstrap script that creates S3/SQS and both Lambdas
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro

      # 3) Your .env so bootstrap can source DB + queue names
      - ./.env:/etc/localstack/init/ready.d/.env:ro

      # 4) Built Lambda ZIPs (if your bootstrap expects them here)
      #   Adjust if your build script uses a different folder.
      - ./lambda_bundles:/opt/lambda_bundles

    restart: unless-stopped
