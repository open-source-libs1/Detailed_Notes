# Artifactory credentials - DO NOT COMMIT
export ART_USER="your_artifactory_username"
export ART_TOKEN="your_artifactory_identity_token"

# Host and repo path
export ART_HOST="artifactory.cloud.capitalone.com"
export ART_INDEX_PATH="/artifactory/api/pypi/pypi-internalfacing/simple"


/////////////


#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

PY310="/opt/homebrew/bin/python3.10"

echo "========== [1] Verify Python 3.10 =========="
if [[ ! -x "$PY310" ]]; then
  echo "ERROR: $PY310 not found."
  echo "Install it with: brew install python@3.10"
  exit 1
fi
"$PY310" --version
echo

echo "========== [2] Verify .env.artifactory =========="
if [[ ! -f ".env.artifactory" ]]; then
  echo "ERROR: .env.artifactory not found in repo root."
  exit 1
fi

# shellcheck disable=SC1091
source ".env.artifactory"

: "${ART_USER:?ART_USER is not set in .env.artifactory}"
: "${ART_TOKEN:?ART_TOKEN is not set in .env.artifactory}"
: "${ART_HOST:?ART_HOST is not set in .env.artifactory}"
: "${ART_INDEX_PATH:?ART_INDEX_PATH is not set in .env.artifactory}"

AUTH_INDEX_URL="https://${ART_USER}:${ART_TOKEN}@${ART_HOST}${ART_INDEX_PATH}"
MASKED_URL="https://${ART_USER}:****@${ART_HOST}${ART_INDEX_PATH}"

echo "Using Artifactory index: ${MASKED_URL}"
echo

echo "========== [3] Verify Artifactory access =========="
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${AUTH_INDEX_URL}/" || true)"
echo "Artifactory HTTP status: ${HTTP_CODE}"
if [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "301" && "${HTTP_CODE}" != "302" ]]; then
  echo "ERROR: Cannot access Artifactory with provided credentials."
  exit 2
fi
echo

echo "========== [4] Export pip/pipenv env vars =========="
export PIP_INDEX_URL="${AUTH_INDEX_URL}"
export PIPENV_PYPI_MIRROR="${AUTH_INDEX_URL}"
export PIP_TRUSTED_HOST="${ART_HOST}"
unset PIP_EXTRA_INDEX_URL || true
echo "Environment variables set."
echo

echo "========== [5] Recreate virtualenv with Python 3.10 =========="
pipenv --rm >/dev/null 2>&1 || true
pipenv --python "$PY310"
pipenv run python --version
echo

echo "========== [6] Test direct package install =========="
pipenv run pip install --index-url "${AUTH_INDEX_URL}" PyYAML
echo "PyYAML install test passed."
echo

echo "========== [7] Generate Pipfile.lock =========="
rm -f Pipfile.lock
pipenv lock --clear
echo

echo "========== [8] Verify lock =========="
grep -n '"requests"' Pipfile.lock || true
grep -n '"pyyaml"' Pipfile.lock || true
echo

echo "SUCCESS: Pipfile.lock generated with Python 3.10"
