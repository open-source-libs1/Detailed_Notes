# Build client (install client dev deps first to avoid webpack-cli prompt)
RUN cd client && npm install --include=dev --no-audit --no-fund
RUN cd client && npm run build

# After build, prune dev deps for runtime image
RUN npm prune --omit=dev


//////////////////


export DOCKER_BUILDKIT=1
source .env

docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -t payout-ui:local .
