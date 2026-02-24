DOCKER_BUILDKIT=1 docker build --progress=plain \
  --build-arg app_env=local \
  --build-arg oneingest_application=BAOFFERFULFILLMENTENGINE \
  --build-arg oneingest_schema=deposit_market_decide_incentive_fulfillment_status_updated_v2 \
  --build-arg devexchange_url=https://api-it.cloud.capitalone.com \
  --build-arg client_id=3ba05106a04b4faf8af63d1a8c3c58f8 \
  --build-arg http_proxy=${HTTP_PROXY} \
  --build-arg https_proxy=${HTTPS_PROXY} \
  --build-arg no_proxy=${NO_PROXY} \
  --build-arg DX_CLIENT_SECRET=${CLIENT_SECRET} \
  -t f1000-docker .


    ///////////////////


docker run --rm -it -v "$HOME:/host" artifactory-edge-staging.cloud.capitalone.com/baenterprisesharedimages-docker/languages/node:22-ubuntu24.04-202602231446 bash


npm config set registry https://artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/
npm login --registry=https://artifactory.cloud.capitalone.com/artifactory/api/npm/npm-internalfacing/
cp /root/.npmrc /host/.npmrc-f1000
exit


RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm install
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm install --production


export DOCKER_BUILDKIT=1
docker build --progress=plain --secret id=npmrc,src=$HOME/.npmrc-f1000 -t f1000-docker .

