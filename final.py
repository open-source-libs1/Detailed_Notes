version: "3.9"

services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4
    container_name: localstack

    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"

    environment:
      # Pro image, but Pro features OFF
      - ACTIVATE_PRO=0

      # Required services
      - SERVICES=s3,sqs,iam,lambda,cloudwatch,logs

      # 🔑 run lambdas in-process, no docker runtime
      - LAMBDA_EXECUTOR=local

      # Dummy creds/region for SDKs & CLI
      - AWS_DEFAULT_REGION=us-east-1
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test

      # Extra logging while we iterate
      - DEBUG=1

    volumes:
      # Project code (not strictly needed by LS but harmless and handy)
      - ".:/project"

      # Bootstrap script that creates S3/SQS + wires lambdas
      - "./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro"

      # Built lambda zips
      - "./.localstack/artifacts:/artifacts"

      # ❌ no /tmp/localstack bind-mount anymore
      # ❌ no /var/run/docker.sock needed now

    # Optional healthcheck
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:4566/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 40s
