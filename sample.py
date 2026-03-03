npm install --include=dev --workspaces --include-workspace-root --legacy-peer-deps --no-audit --no-fund; \

# Create npm auth config using BuildKit secret (token is NOT stored in image layers)
RUN --mount=type=secret,id=npm_token \
    set -euo pipefail; \
    cp .npmrc.template /root/.npmrc; \
    printf "\n//artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/:_authToken=%s\n" \
      "$(cat /run/secrets/npm_token)" >> /root/.npmrc; \
    npm install --include=dev --workspaces --include-workspace-root --legacy-peer-deps --no-audit --no-fund; \
    rm -f /root/.npmrc


///////////////////


# Build client (no interactive webpack-cli prompt)
RUN npm --workspace client run build


/////////////////

RUN npm prune --omit=dev --workspaces --include-workspace-root


/////////////////


RUN cd client && echo "yes" | npm install webpack webpack-cli mini-css-extract-plugin && npm install && npm install --dev
RUN cd client && npm run build


///////////////////


export DOCKER_BUILDKIT=1
docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -t payout-ui:local .  
