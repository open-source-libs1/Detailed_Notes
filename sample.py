# Create npm auth config using BuildKit secret (token is NOT stored in image layers)
RUN --mount=type=secret,id=npm_token \
    sh -c 'cat .npmrc.template > /root/.npmrc && \
           printf "\n//artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/:_authToken=%s\n" "$(cat /run/secrets/npm_token)" >> /root/.npmrc'
