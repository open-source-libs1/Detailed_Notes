
version: "3.9"

services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4
    container_name: localstack

    ports:
      - "4566:4566"
      - "4510-4559:4510-4559"

    # Optional but nice to have
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "-T", "1", "http://localhost:2019/metrics", "-O", "-"]
      interval: 90s
      timeout: 10s
      retries: 3
      start_period: 40s

    environment:
      # Run without Pro license token
      - ACTIVATE_PRO=0

      # Services we actually need
      - SERVICES=s3,sqs,iam,lambda,cloudwatch,logs

      # 🔴 CRITICAL: use internal Lambda-compatible image, not plain python
      - 'LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12": "artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}'

      - DEBUG=1
      - AWS_DEFAULT_REGION=us-east-1

      # Let LocalStack start Docker containers for Lambda runtimes
      - DOCKER_HOST=unix:///var/run/docker.sock

    volumes:
      # Docker socket for Lambda containers
      - "/var/run/docker.sock:/var/run/docker.sock"

      # Your repo (optional, handy for debugging from inside container)
      - ".:/project"

      # Your bootstrap script – same one we’ve been iterating on
      - "./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro"

      # Lambda ZIP build/artifacts directory
      - "./.localstack/artifacts:/artifacts"

    restart: unless-stopped
