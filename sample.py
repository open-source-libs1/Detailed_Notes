# 1) make output match Jenkins
export DOCKER_BUILDKIT=1

# 2) run the build exactly (use whatever tag you want)
docker build --progress=plain -f Dockerfile.build -t node24-build-test .


/////////////////

# Create/ensure Jenkins user/group (Wolfi/Alpine) - no getent dependency
RUN set -eux; \
    # group: create only if name AND gid are absent
    if ! grep -qE '^jenkins:' /etc/group 2>/dev/null && ! grep -qE '^[^:]*:[^:]*:54902:' /etc/group 2>/dev/null; then \
      addgroup -S -g 54902 jenkins; \
    else \
      echo "Group already present (name jenkins and/or gid 54902)"; \
    fi; \
    \
    # user: create only if name AND uid are absent
    if ! grep -qE '^jenkins:' /etc/passwd 2>/dev/null && ! grep -qE '^[^:]*:[^:]*:54902:' /etc/passwd 2>/dev/null; then \
      adduser -S -u 54902 -G jenkins -h "${GIT_HOME_DIR}" jenkins; \
    else \
      echo "User already present (name jenkins and/or uid 54902)"; \
    fi; \
    \
    mkdir -p "${GIT_HOME_DIR}"; \
    chown -R 54902:54902 "${GIT_HOME_DIR}"


docker build --no-cache --progress=plain -f Dockerfile.build -t node24-build-test .


IMG="artifactory-edge-staging.cloud.capitalone.com/baenterprisesharedimages-docker/languages/node:24-dev-chainguard-202602261420"
docker run --rm --entrypoint sh "$IMG" -lc 'cat /etc/group | grep -n jenkins || true; cat /etc/passwd | grep -n jenkins || true'
