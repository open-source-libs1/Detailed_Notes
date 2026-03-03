# Create npm auth config using BuildKit secret (token is NOT stored in image layers)
# Use npm install (NOT npm ci) because this repo doesn't have package-lock.json
RUN --mount=type=secret,id=npm_token \
    set -euo pipefail; \
    cp .npmrc.template /root/.npmrc; \
    printf "\n//artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/:_authToken=%s\n" \
      "$(cat /run/secrets/npm_token)" >> /root/.npmrc; \
    npm install --include-workspace-root --no-audit --no-fund; \
    rm -f /root/.npmrc



////////////////////

export DOCKER_BUILDKIT=1

source .env
test -n "${ARTIFACTORY_IDENTITY_TOKEN:-}" && echo "token is set" || echo "token missing"

docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -f Dockerfile \
  -t payout-ui:local .


docker run --rm -it -p 3001:3001 --env-file .env payout-ui:local
