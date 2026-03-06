docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -t payout-ui:local .

docker image inspect payout-ui:local --format '{{json .Config.User}}'


/////////////

export DOCKER_BUILDKIT=1
source .env

docker build --no-cache --progress=plain \
  --secret id=npm_token,env=ARTIFACTORY_IDENTITY_TOKEN \
  -t payout-ui:local .
