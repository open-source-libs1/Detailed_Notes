WORKDIR /src
COPY --from=builder /src /src
COPY --from=builder /src /app
COPY sm_secrets.yaml /src/sm_secrets.yaml
COPY sm_secrets.yaml /app/sm_secrets.yaml

USER 1000

EXPOSE ${APP_PORT}
CMD ["node", "/src/app/index.js"]
