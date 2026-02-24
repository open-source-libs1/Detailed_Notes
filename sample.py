auth-type=legacy
registry=https://artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/
always-auth=true

export DOCKER_BUILDKIT=1
printf "%s" "$NPM_TOKEN" | docker build \
  --secret id=npm_token,src=/dev/stdin \
  -t f1000-docker .


RUN --mount=type=secret,id=npm_token \
    sh -c 'printf "auth-type=legacy\nregistry=https://artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/\nalways-auth=true\n//artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/:_authToken=%s\n" "$(cat /run/secrets/npm_token)" > /root/.npmrc'
