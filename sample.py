# Build output / runtime files
COPY sm_secrets.yaml /app/sm_secrets.yaml

# If runtime needs these dirs, create them before dropping privileges
USER root
RUN mkdir -p /app /src /tmp/app && chmod 1777 /tmp/app

# Distroless-safe: use numeric user, not named user
USER 1000

EXPOSE ${APP_PORT}
CMD ["node", "/app/index.js"]



////////////////////


docker image inspect payout-ui:local --format '{{json .Config.User}}'


/////////////////////

docker run --rm --entrypoint sh payout-ui:local -lc 'cat /etc/passwd || true'


  ////////////////////


  COPY . /app
COPY sm_secrets.yaml /app/sm_secrets.yaml

USER root
RUN mkdir -p /tmp/app && chmod 1777 /tmp/app

USER 1000

EXPOSE ${APP_PORT}
CMD ["node", "/app/index.js"]



  /////////////////

docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -t payout-ui:local .

docker image inspect payout-ui:local --format '{{json .Config.User}}'
  
