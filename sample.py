WORKDIR /src

COPY --from=builder --chown=1000:1000 /src /src
COPY --chown=1000:1000 sm_secrets.yaml /app/sm_secrets.yaml
COPY --chown=1000:1000 sm_secrets.yaml /src/sm_secrets.yaml

USER 1000

EXPOSE ${APP_PORT}

CMD ["node", "/src/app/index.js"]
