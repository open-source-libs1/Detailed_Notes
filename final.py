
services:
  localstack:
    image: localstack/localstack:4.10
    container_name: localstack
    ports:
      - "4566:4566"
      - "4510-4559:4510-4559"
    environment:
      - SERVICES=s3,sqs,lambda,iam,cloudwatch,logs
      - AWS_DEFAULT_REGION=us-east-1
      - DEBUG=1

      # Docker-in-Docker so LocalStack can start runtime containers
      - DOCKER_HOST=unix:///var/run/docker.sock

      # 🔴 IMPORTANT: map Python 3.12 runtime to your internal image
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-edge-staging.cloud.capitalone.com/baenterprisesharedimages-docker/languages/python:3.12-alpine3.21-251103"}

    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
      - ".:/project"
      - "./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh"
      - "./.localstack/artifacts:/artifacts"
