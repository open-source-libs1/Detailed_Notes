# Install client deps and build client
RUN cd client && npm install --legacy-peer-deps --no-audit --no-fund
RUN cd client && npm run build

# Build output / runtime files
COPY sm_secrets.yaml /app/sm_secrets.yaml

# If runtime needs these dirs, create them before dropping privileges
USER root
RUN mkdir -p /app /src /tmp/app && chmod 1777 /tmp/app

# Distroless-safe: use numeric user, not named user
USER 1000

EXPOSE ${APP_PORT}
CMD ["node", "/app/index.js"]


/////////////////

export DOCKER_BUILDKIT=1
source .env

docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -t payout-ui:local .
