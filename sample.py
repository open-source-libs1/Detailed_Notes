
#!/usr/bin/env bash

# Build docker based on local setup, but do NOT inject runtime secrets.
# Goal: mimic dev more closely and validate secret-manager/runtime loading.

set -euo pipefail

: "${NPM_TOKEN:?NPM_TOKEN is required for docker build (Artifactory auth).}"
: "${HTTP_PROXY:=}"
: "${OAUTH_WEBACCESS_URL:=https://authn-qa.capitalone.com}"
: "${SSO_REDIRECT_URI:=http://localhost:3001/payout/}"

export DOCKER_BUILDKIT=1

printf "%s" "$NPM_TOKEN" | docker build \
  --no-cache \
  --secret id=npm_token,src=/dev/stdin \
  --build-arg app_env=local \
  --build-arg oneingest_application=BAOFFERFULFILLMENTENGINE \
  --build-arg oneingest_schema=deposit_market_decide_incentive_fulfillment_status_updated_v2 \
  --build-arg devexchange_url=https://api-it.cloud.capitalone.com \
  --build-arg client_id=3ba05106a04b4faf8af63d1a8c3c58f8 \
  --build-arg http_proxy="${HTTP_PROXY}" \
  --build-arg oauth_webaccess_url="${OAUTH_WEBACCESS_URL}" \
  --build-arg sso_redirect_uri="${SSO_REDIRECT_URI}" \
  -t f1000-docker .

# app_env is local for local testing
# Intentionally NOT passing DX_CLIENT_SECRET or OAUTH_CLIENT_SECRET here.
# That is the whole point of this parity test.

docker run --rm -p 3001:3001 \
  -e APP_ENV=local \
  -e OAUTH_WEBACCESS_URL="${OAUTH_WEBACCESS_URL}" \
  -e SSO_REDIRECT_URI="${SSO_REDIRECT_URI}" \
  f1000-docker
