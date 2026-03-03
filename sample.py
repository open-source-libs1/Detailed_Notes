# syntax=docker/dockerfile:1.7

# (you already have WORKDIR /src and COPY . /src above this)

# Create npm auth config using BuildKit secret (token is NOT stored in image layers)
RUN --mount=type=secret,id=npm_token \
    set -euo pipefail; \
    cp .npmrc.template /root/.npmrc; \
    printf "\n//artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/:_authToken=%s\n" \
      "$(cat /run/secrets/npm_token)" >> /root/.npmrc; \
    npm ci; \
    rm -f /root/.npmrc

# Build client (needs dev deps installed above)
RUN cd client && npm run build

# After build, prune dev deps for runtime image
RUN npm prune --omit=dev



/////////////////


# 1) Load your env locally (your screenshot shows ARTIFACTORY_IDENTITY_TOKEN is in here)
source .env

# 2) MUST enable BuildKit so --secret works
export DOCKER_BUILDKIT=1

# 3) Build, passing the token into build as a secret
docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -t payout-ui:test .
