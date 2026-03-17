# final runtime stage
WORKDIR /src
COPY --from=builder --chown=1000:1000 /src /src
COPY --chown=1000:1000 sm_secrets.yaml /app/sm_secrets.yaml

USER 1000

EXPOSE ${APP_PORT}
CMD ["node", "app/index.js"]
