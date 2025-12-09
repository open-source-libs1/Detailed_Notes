
version: "3.9"

services:
  localstack:
    # Use your internal LocalStack image (same one you showed in the screenshot)
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4
    container_name: localstack

    ports:
      - "127.0.0.1:4566:4566"          # main edge endpoint
      - "127.0.0.1:4510-4559:4510-4559" # lambda debug ports (optional)

    environment:
      # We are using the Pro image but NOT activating Pro features
      - ACTIVATE_PRO=0

      # Only the services we actually use
      - SERVICES=s3,sqs,iam,lambda,cloudwatch,logs

      # 🔑 Force LocalStack to execute Lambdas in-process, not via Docker runtime
      - LAMBDA_EXECUTOR=local

      # Region + dummy creds (must be set for AWS CLI / SDKs, but values don't matter)
      - AWS_DEFAULT_REGION=us-east-1
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test

      # Verbose logging while we iterate
      - DEBUG=1

    volumes:
      # Mount repo so LocalStack can read bootstrap + artifacts
      - ".:/project"

      # Bootstrap script that creates S3/SQS and wires the Lambdas
      - "./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro"

      # Lambda deployment zips from build_lambdas.sh
      - "./.localstack/artifacts:/artifacts"

      # Optional: dedicated temp dir so LocalStack can cache stuff
      - "./.localstack/tmp:/tmp/localstack"

    # Optional, but nice to have
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:4566/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 40s
