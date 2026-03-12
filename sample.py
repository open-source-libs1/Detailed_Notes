FROM artifactory-edge-staging.cloud.capitalone.com/baenterprisesharedimages-docker/languages/node:24-dev-chainguard-202602261420 AS builder

ARG app_env
ARG app_port=3001
ARG aws_region=us-east-1
ARG oneingest_application
ARG oneingest_schema
ARG devexchange_url
ARG client_id
ARG DX_CLIENT_SECRET
ARG sha
ARG updated
ARG http_proxy
ARG no_proxy=169.254.169.254,s3.amazonaws.com,.s3.amazonaws.com,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com
ARG OAUTH_CLIENT_ID
ARG oauth_client_secret
ARG oauth_webaccess_url
ARG sso_redirect_uri=http://localhost:3001/
ARG SLACK_WEBHOOK
ARG AWS_BUCKET_NAME
ARG AWS_PAYOUT_MANUAL_UPLOAD_FOLDER
ARG COF_SM_ENABLED
ARG COF_SM_ENVIRONMENT

LABEL ownercontact="TheLabskies@capitalone.com"
LABEL asv=ASVOFFERFULFILLMENTENGINE
LABEL ba=BAOFFERFULFILLMENTENGINE

ENV NODE_ENV=production \
    NODE_TLS_REJECT_UNAUTHORIZED=0 \
    APP_ENV=${app_env:-dev} \
    APP_PORT=${app_port} \
    DX_CLIENT_SECRET=${DX_CLIENT_SECRET} \
    ONEINGEST_APPLICATION=${oneingest_application} \
    ONEINGEST_SCHEMA=${oneingest_schema} \
    DEVEXCHANGE_URL=${devexchange_url} \
    CLIENT_ID=${client_id} \
    IMAGE_BUILT_DATE=${updated} \
    DOCKER_IMAGE_TAG=${app_env:-dev} \
    OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID:-84b48152-3546-4477-8e5e-3b5ba5512e44} \
    OAUTH_CLIENT_SECRET=${oauth_client_secret} \
    SSO_REDIRECT_URI=${sso_redirect_uri} \
    OAUTH_WEBACCESS_URL=${oauth_webaccess_url} \
    REGION=${aws_region} \
    HTTPS_PROXY=${http_proxy} \
    HTTP_PROXY=${http_proxy} \
    http_proxy=${http_proxy} \
    https_proxy=${http_proxy} \
    NO_PROXY=${no_proxy} \
    no_proxy=${no_proxy} \
    SLACK_WEBHOOK=${SLACK_WEBHOOK} \
    AWS_BUCKET_NAME=${AWS_BUCKET_NAME} \
    AWS_PAYOUT_MANUAL_UPLOAD_FOLDER=${AWS_PAYOUT_MANUAL_UPLOAD_FOLDER} \
    COF_SM_ENABLED=${COF_SM_ENABLED} \
    COF_SM_ENVIRONMENT=${COF_SM_ENVIRONMENT}

WORKDIR /src
COPY . /src

RUN ["apk", "add", "--no-cache", "coreutils"]

RUN ["npm", "install"]
RUN ["npm", "install", "--production"]
RUN ["npm", "install", "--save", "@opentelemetry/api"]
RUN ["npm", "install", "--save", "@opentelemetry/auto-instrumentations-node"]

WORKDIR /src/client
RUN ["npm", "install", "--legacy-peer-deps", "--no-audit", "--no-fund"]
RUN ["npm", "run", "build"]


FROM artifactory-edge-staging.cloud.capitalone.com/baenterprisesharedimages-docker/languages/node:24-chainguard-202603111416

ARG app_env
ARG app_port=3001
ARG aws_region=us-east-1
ARG oneingest_application
ARG oneingest_schema
ARG devexchange_url
ARG client_id
ARG DX_CLIENT_SECRET
ARG sha
ARG updated
ARG http_proxy
ARG no_proxy=169.254.169.254,s3.amazonaws.com,.s3.amazonaws.com,.kdc.capitalone.com,.cloud.capitalone.com,.clouddqt.capitalone.com
ARG OAUTH_CLIENT_ID
ARG oauth_client_secret
ARG oauth_webaccess_url
ARG sso_redirect_uri=http://localhost:3001/
ARG SLACK_WEBHOOK
ARG AWS_BUCKET_NAME
ARG AWS_PAYOUT_MANUAL_UPLOAD_FOLDER
ARG COF_SM_ENABLED
ARG COF_SM_ENVIRONMENT

LABEL ownercontact="TheLabskies@capitalone.com"
LABEL asv=ASVOFFERFULFILLMENTENGINE
LABEL ba=BAOFFERFULFILLMENTENGINE

ENV NODE_ENV=production \
    NODE_TLS_REJECT_UNAUTHORIZED=0 \
    APP_ENV=${app_env:-dev} \
    APP_PORT=${app_port} \
    DX_CLIENT_SECRET=${DX_CLIENT_SECRET} \
    ONEINGEST_APPLICATION=${oneingest_application} \
    ONEINGEST_SCHEMA=${oneingest_schema} \
    DEVEXCHANGE_URL=${devexchange_url} \
    CLIENT_ID=${client_id} \
    IMAGE_BUILT_DATE=${updated} \
    DOCKER_IMAGE_TAG=${app_env:-dev} \
    OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID:-84b48152-3546-4477-8e5e-3b5ba5512e44} \
    OAUTH_CLIENT_SECRET=${oauth_client_secret} \
    SSO_REDIRECT_URI=${sso_redirect_uri} \
    OAUTH_WEBACCESS_URL=${oauth_webaccess_url} \
    REGION=${aws_region} \
    HTTPS_PROXY=${http_proxy} \
    HTTP_PROXY=${http_proxy} \
    http_proxy=${http_proxy} \
    https_proxy=${http_proxy} \
    NO_PROXY=${no_proxy} \
    no_proxy=${no_proxy} \
    SLACK_WEBHOOK=${SLACK_WEBHOOK} \
    AWS_BUCKET_NAME=${AWS_BUCKET_NAME} \
    AWS_PAYOUT_MANUAL_UPLOAD_FOLDER=${AWS_PAYOUT_MANUAL_UPLOAD_FOLDER} \
    COF_SM_ENABLED=${COF_SM_ENABLED} \
    COF_SM_ENVIRONMENT=${COF_SM_ENVIRONMENT}

WORKDIR /app
COPY --from=builder /src /app
COPY sm_secrets.yaml /app/sm_secrets.yaml

USER 1000

EXPOSE ${APP_PORT}
CMD ["node", "/app/index.js"]
