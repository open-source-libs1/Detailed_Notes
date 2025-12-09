LOCALSTACK_AUTH_TOKEN=ls-XXXXXXXX-your-token-here


services:
  localstack:
    image: localstack/localstack-pro:4        # or your corp mirror of pro
    environment:
      - AWS_DEFAULT_REGION=us-east-1
      - DEBUG=1
      - DOCKER_HOST=unix:///var/run/docker.sock
      - LAMBDA_RUNTIME_IMAGE_MAPPING={"python3.12":"artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}
      - HOSTNAME_EXTERNAL=localstack
      - LOCALSTACK_HOST=localstack
      - LOCALSTACK_AUTH_TOKEN=${LOCALSTACK_AUTH_TOKEN}   # << NEW
      # DO NOT set ACTIVATE_PRO=0 if you want Pro
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro
      - ./.env:/etc/localstack/init/ready.d/.env:ro
      - ./.localstack:/artifacts
