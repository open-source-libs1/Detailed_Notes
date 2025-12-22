#!/usr/bin/env bash
set -euo pipefail

# Always run from the folder where this script lives (localstack/)
HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE_DIR}"

echo "[run] PWD=$(pwd)"
echo "[run] Building lambda ZIP(s) locally..."
./build_lambdas.sh

echo "[run] Starting docker compose..."
# docker compose already uses docker-compose.yml in this same folder
docker compose up --build
