services:
  localstack:
    # ... keep everything else the same

    healthcheck:
      # Healthy only when:
      #  1) LocalStack API is up
      #  2) The DB secret exists (provisioned by 00-enrollment-init.sh)
      test:
        [
          "CMD-SHELL",
          "curl -fsS http://localhost:4566/health >/dev/null \
           && awslocal secretsmanager describe-secret --secret-id \"${SECRET_ARN:-enrollment-db-local}\" >/dev/null 2>&1"
        ]
      interval: 10s
      timeout: 5s
      retries: 60
      start_period: 20s

  enrollment-writer:
    # ... keep everything else the same
    depends_on:
      localstack:
        condition: service_healthy
