# Ensure we can change ownership (Chainguard/Wolfi images often default to non-root)
USER root

# Make sure directories exist before chown
RUN mkdir -p /src /app

# If you need /src and /app owned by appuser
RUN chown -R appuser:appuser /src /app

# You already have this copy (keep it)
COPY --chown=appuser:appuser sm_secrets.yaml /app/sm_secrets.yaml

# Drop back to non-root
USER appuser

///////////////////////////


docker build --no-cache --progress=plain -f Dockerfile.build -t node24-build-test .


////////////////

export DOCKER_BUILDKIT=1
docker build --progress=plain -f Dockerfile -t payout-ui:test .

/////////////////////


docker run --rm -it --entrypoint /bin/sh payout-ui:test -lc 'getent passwd appuser || grep appuser /etc/passwd || true'
