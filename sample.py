# Install client deps (avoid webpack-cli prompt) and build client
RUN cd client && npm install --include=dev --legacy-peer-deps --no-audit --no-fund
RUN cd client && npm run build
