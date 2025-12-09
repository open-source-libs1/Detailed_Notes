version: "3.9"

services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4
    container_name: localstack

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"

    environment:
      # Basic AWS / debug
      - AWS_DEFAULT_REGION=us-east-1
      - DEBUG=1

      # Let LocalStack talk to the host Docker daemon (needed for Lambda containers)
      - DOCKER_HOST=unix:///var/run/docker.sock

      # Use your internal Lambda base image instead of public.ecr.aws
      # (must be one JSON line, no spaces)
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}

      # Make the container think of itself as "localstack"
      - HOSTNAME_EXTERNAL=localstack
      - LOCALSTACK_HOST=localstack

      # Services we actually need
      - SERVICES=s3,sqs,iam,lambda,cloudwatch,logs

      # Simple fake credentials (LocalStack ignores them but AWS CLI wants them)
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test

    volumes:
      # 1) Host Docker socket → required for running Lambda containers
      - /var/run/docker.sock:/var/run/docker.sock

      # 2) Bootstrap script that creates S3/SQS + Lambdas
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro

      # 3) .env so bootstrap can read DB + queue names (it looks at /project/.env)
      - ./.env:/project/.env:ro

      # 4) Lambda ZIPs – your build drops them in ./.localstack/artifacts on the host
      #    Bootstrap expects them at /artifacts inside the container
      - ./.localstack/artifacts:/artifacts:ro

    restart: unless-stopped
