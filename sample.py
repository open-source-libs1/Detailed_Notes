COPY --chown=65532:65532 sm_secrets.yaml /app/sm_secrets.yaml

RUN mkdir -p /src/target/logs && chown -R 65532:65532 /src/target

USER 65532:65532

EXPOSE ${APP_PORT}

CMD ["node", "app/index.js"]
