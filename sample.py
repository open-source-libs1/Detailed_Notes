# ... everything above stays the same ...

# keep this (you already had it)
COPY --chown=appuser:appuser sm_secrets.yaml /app/sm_secrets.yaml

# Avoid recursive chown (often fails in Jenkins/rootless builders)
# Just ensure dirs exist; keep runtime user as appuser.
USER root
RUN mkdir -p /src /app

# (Optional) writable scratch for runtime if needed (safe)
RUN mkdir -p /tmp/app && chmod 1777 /tmp/app

# No more: RUN chown -R appuser:appuser /src /app   <-- REMOVE THIS

# You already have this copy; keep ONLY ONE copy line (remove the duplicate)
# COPY --chown=appuser:appuser sm_secrets.yaml /app/sm_secrets.yaml

USER appuser

EXPOSE ${APP_PORT}
CMD ["node", "/app/index.js"]


/////////////////////


export DOCKER_BUILDKIT=1
docker build --no-cache --progress=plain -f Dockerfile -t payout-ui:test .
