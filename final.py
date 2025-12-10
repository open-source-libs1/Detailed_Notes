version: "3.8"

services:
  localstack:
    image: artifactory-dockerhub.cloud.capitalone.com/localstack/localstack-pro:4.8
    container_name: localstack
    ports:
      - "127.0.0.1:4566:4566"
      - "127.0.0.1:4510-4559:4510-4559"
    environment:
      ACTIVATE_PRO: "1"
      SERVICES: "s3,sqs,logs,lambda,iam,cloudwatch"
      DEBUG: "1"
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"
      LOCALSTACK_AUTH_TOKEN: "${LOCALSTACK_AUTH_TOKEN}"
      DOCKER_HOST: "unix:///var/run/docker.sock"
      LAMBDA_RUNTIME_IMAGE_MAPPING: >
        {"python3.12": "artifactory-ecr.cloud.capitalone.com/lambda/python:3.12"}
      LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT: "600000"
      HOSTNAME_EXTERNAL: "localstack"
      LOCALSTACK_HOST: "localstack"

      HTTP_PROXY: "${HTTP_PROXY}"
      HTTPS_PROXY: "${HTTPS_PROXY}"
      NO_PROXY: "${NO_PROXY:-localhost,127.0.0.1,localstack,host.docker.internal}"

      OUTBOUND_HTTP_PROXY: "${HTTP_PROXY}"
      OUTBOUND_HTTPS_PROXY: "${HTTPS_PROXY}"

      REQUESTS_CA_BUNDLE: "/root/certs/C1G2RootCA.crt"
      CURL_CA_BUNDLE: "/root/certs/C1G2RootCA.crt"
      NODE_EXTRA_CA_CERTS: "/root/certs/C1G2RootCA.crt"

    volumes:
      - "${HOME}/certs:/root/certs:ro"
      - "./.volume:/var/lib/localstack"
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "./localstack_bootstrap.sh:/etc/localstack/init/ready.d/00-bootstrap.sh:ro"
      - "./.env:/project/.env:ro"
      - "./.localstack/artifacts:/artifacts:ro"
    restart: unless-stopped

  ########################################################
  # EnrollmentWriter ECS-style worker (local dev)
  ########################################################
  enrollment-writer:
    # ⬇️ instead of pulling python:3.12 from Docker Hub, build from your repo Dockerfile
    build:
      context: .
      dockerfile: Dockerfile
    image: enrollment-writer-local
    container_name: enrollment-writer
    depends_on:
      - localstack
    working_dir: /app

    volumes:
      # adjust if your app path is slightly different inside the built image
      - "./enrollment_writer:/app"

    environment:
      AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-us-east-1}"
      AWS_ENDPOINT_URL: "http://localstack:4566"
      AWS_ACCESS_KEY_ID: "localstack"
      AWS_SECRET_ACCESS_KEY: "localstack"

      SOURCE_SQS_QUEUE_URL: "http://localstack:4566/000000000000/${ENROLLMENT_QUEUE_NAME}"

      LOG_LEVEL: "DEBUG"

      DB_HOST: "${DB_HOST}"
      DB_PORT: "${DB_PORT}"
      DB_NAME: "${DB_NAME}"
      DB_USER: "${DB_USER}"
      DB_PASSWORD: "${DB_PASSWORD}"

      # pass proxies into the app container too, in case it needs outbound access
      HTTP_PROXY: "${HTTP_PROXY}"
      HTTPS_PROXY: "${HTTPS_PROXY}"
      NO_PROXY: "${NO_PROXY:-localhost,127.0.0.1,localstack,host.docker.internal}"

    command: ["python", "app/main.py"]
    restart: unless-stopped
