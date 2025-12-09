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
