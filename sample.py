# 1) make output match Jenkins
export DOCKER_BUILDKIT=1

# 2) run the build exactly (use whatever tag you want)
docker build --progress=plain -f Dockerfile.build -t node24-build-test .


/////////////////


IMG="artifactory-edge-staging.cloud.capitalone.com/baenterprisesharedimages-docker/languages/node:24-chainguard-202602191703"

docker run --rm -it --entrypoint sh "$IMG" -lc '
set -eux
id
cat /etc/os-release || true
which apk || true
ls -l /etc/apk || true
cat /etc/apk/repositories || true

# try the same command that fails in Jenkins
apk update
apk add --no-cache git
'
