# 1) make output match Jenkins
export DOCKER_BUILDKIT=1

# 2) run the build exactly (use whatever tag you want)
docker build --progress=plain -f Dockerfile.build -t node24-build-test .
