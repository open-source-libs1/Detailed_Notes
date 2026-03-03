# 1) make output match Jenkins
export DOCKER_BUILDKIT=1

# 2) run the build exactly (use whatever tag you want)
docker build --progress=plain -f Dockerfile.build -t node24-build-test .


/////////////////

# Create Jenkins user/group (Wolfi/Alpine style)
RUN addgroup -g 54902 -S jenkins \
 && adduser  -u 54902 -S -G jenkins -h ${GIT_HOME_DIR} jenkins \
 && mkdir -p ${GIT_HOME_DIR} \
 && chown -R 54902:54902 ${GIT_HOME_DIR}

USER 54902
WORKDIR ${GIT_HOME_DIR}
