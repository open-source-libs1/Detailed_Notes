export DOCKER_BUILDKIT=1

printf "%s" "$NPM_TOKEN" | docker build \
  --secret id=npm_token,src=/dev/stdin \
  --build-arg app_env=local \
  --build-arg oneingest_application=BAOFFERFULFILLMENTENGINE \
  --build-arg oneingest_schema=deposit_market_decide_incentive_fulfillment_status_updated_v2 \
  --build-arg devexchange_url=https://api-it.cloud.capitalone.com \
  --build-arg client_id=3ba05106a04b4faf8af63d1a8c3c58f8 \
  --build-arg http_proxy=${HTTP_PROXY} \
  --build-arg DX_CLIENT_SECRET=${CLIENT_SECRET} \
  -t f1000-docker .



    docker run -p 3001:3001 --network container_default f1000-docker
