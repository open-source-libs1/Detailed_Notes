WORKDIR /src

COPY . /src

# Install server dependencies
RUN npm install
RUN echo "yes" | npm install --production

# Auto instrumentation
RUN npm install --save @opentelemetry/api \
 && npm install --save @opentelemetry/auto-instrumentations-node

# Build client in BUILD image, not runtime image
WORKDIR /src/client
RUN npm install --legacy-peer-deps --no-audit --no-fund
RUN npm run build

# Return to repo root
WORKDIR /src


/////////////////////////


# Runtime image only - do not run npm install / npm build here
COPY sm_secrets.yaml /app/sm_secrets.yaml

# Copy already-built client assets from build context/artifact path
# Keep this only if your runtime serves the built UI
COPY client/build /app/client/build

# Distroless-safe runtime user
USER 1000

EXPOSE ${APP_PORT}
CMD ["node", "/app/index.js"]



////////////////////



