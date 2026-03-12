FROM artifactory-edge-staging.cloud.capitalone.com/baenterprisesharedimages-docker/languages/node:24-dev-chainguard-202602261420 AS builder

WORKDIR /src
COPY . /src

RUN ["apk","add","--no-cache","coreutils"]

RUN ["npm","install"]
RUN ["npm","install","--production"]

RUN ["npm","install","--save","@opentelemetry/api"]
RUN ["npm","install","--save","@opentelemetry/auto-instrumentations-node"]

WORKDIR /src/client
RUN ["npm","install","--legacy-peer-deps","--no-audit","--no-fund"]
RUN ["npm","run","build"]


////////////////////


WORKDIR /app
COPY --from=builder /src /app
COPY sm_secrets.yaml /app/sm_secrets.yaml

USER 1000

EXPOSE ${APP_PORT}
CMD ["node","/app/index.js"]
