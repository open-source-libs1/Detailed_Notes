# 1) make output match Jenkins
export DOCKER_BUILDKIT=1

# 2) run the build exactly (use whatever tag you want)
docker build --progress=plain -f Dockerfile.build -t node24-build-test .


/////////////////

# Create Jenkins user/group (Wolfi/Alpine style)
# Create/ensure Jenkins user/group (Wolfi/Alpine style) - idempotent
RUN set -eux; \
    # ensure group exists (GID 54902, name jenkins)
    if getent group 54902 >/dev/null 2>&1; then \
      echo "Group with GID 54902 already exists"; \
    elif getent group jenkins >/dev/null 2>&1; then \
      echo "Group 'jenkins' already exists"; \
    else \
      addgroup -g 54902 -S jenkins; \
    fi; \
    # ensure user exists (UID 54902, name jenkins)
    if getent passwd 54902 >/dev/null 2>&1; then \
      echo "User with UID 54902 already exists"; \
    elif getent passwd jenkins >/dev/null 2>&1; then \
      echo "User 'jenkins' already exists"; \
    else \
      adduser -u 54902 -S -G jenkins -h "${GIT_HOME_DIR}" jenkins; \
    fi; \
    mkdir -p "${GIT_HOME_DIR}"; \
    chown -R 54902:54902 "${GIT_HOME_DIR}"}
