cat <<'EOF' > fix_pipenv_312.sh
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(pwd)"
PY312="/opt/homebrew/bin/python3.12"
ART_HOST="artifactory.cloud.capitalone.com"
ART_INDEX_PATH="/artifactory/api/pypi/pypi-internalfacing/simple"
ART_BASE="https://${ART_HOST}${ART_INDEX_PATH}"

echo "==========[ Verify Python 3.12 ]=========="
"$PY312" --version

echo "==========[ Set Artifactory index ]=========="
export PIP_INDEX_URL="$ART_BASE"
export PIP_TRUSTED_HOST="$ART_HOST"

echo "==========[ Ensure pipx exists ]=========="
command -v pipx >/dev/null || brew install pipx

echo "==========[ Install pipenv via pipx ]=========="
pipx uninstall pipenv >/dev/null 2>&1 || true
PIP_INDEX_URL="$PIP_INDEX_URL" PIP_TRUSTED_HOST="$PIP_TRUSTED_HOST" \
pipx install --python "$PY312" pipenv

echo "==========[ Generate Pipfile.lock ]=========="
pipenv --rm >/dev/null 2>&1 || true

export PIPENV_PYTHON="$PY312"

pipenv install --dev
pipenv lock --clear

echo "SUCCESS: Pipfile.lock generated"
EOF
