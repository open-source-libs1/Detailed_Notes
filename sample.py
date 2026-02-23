cat > .env.artifactory <<'EOF'
# Artifactory credentials (do not commit this file)
export ART_USER="REPLACE_ME"
export ART_TOKEN="REPLACE_ME"

# Must match your Pipfile source:
export ART_HOST="artifactory.cloud.capitalone.com"
export ART_INDEX_PATH="/artifactory/api/pypi/pypi-internalfacing/simple"
EOF

////////////////


cat > fix_pipenv_312.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

PY312="/opt/homebrew/bin/python3.12"
if [[ ! -x "$PY312" ]]; then
  echo "ERROR: $PY312 not found. Install with: brew install python@3.12"
  exit 1
fi

if [[ ! -f ".env.artifactory" ]]; then
  echo "ERROR: .env.artifactory not found in repo root."
  echo "Create it (see instructions) and add ART_USER / ART_TOKEN."
  exit 1
fi

# Load creds (file contains export statements)
# shellcheck disable=SC1091
source ".env.artifactory"

: "${ART_USER:?ART_USER is not set in .env.artifactory}"
: "${ART_TOKEN:?ART_TOKEN is not set in .env.artifactory}"
: "${ART_HOST:?ART_HOST is not set in .env.artifactory}"
: "${ART_INDEX_PATH:?ART_INDEX_PATH is not set in .env.artifactory}"

ART_BASE="https://${ART_HOST}${ART_INDEX_PATH}"
AUTH_INDEX_URL="https://${ART_USER}:${ART_TOKEN}@${ART_HOST}${ART_INDEX_PATH}"

echo "==========[ 1) Verify Python ]=========="
"$PY312" --version
echo

echo "==========[ 2) Verify Artifactory access ]=========="
# Use curl with basic auth embedded in URL (do NOT echo full URL)
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${AUTH_INDEX_URL}/" || true)"
echo "Artifactory HTTP status: ${HTTP_CODE}"
if [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "301" && "${HTTP_CODE}" != "302" ]]; then
  echo "ERROR: Cannot access Artifactory with provided creds."
  echo "Expected 200/301/302 but got ${HTTP_CODE}."
  echo "Check ART_USER/ART_TOKEN permissions for internalfacing repo."
  exit 2
fi
echo

echo "==========[ 3) Ensure pipx exists ]=========="
if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx not found; installing via brew..."
  brew install pipx
  pipx ensurepath || true
  export PATH="$HOME/.local/bin:$PATH"
fi
pipx --version
echo

echo "==========[ 4) Install pipenv via pipx (Python 3.12) ]=========="
# Ensure pipx uses the authenticated index
export PIP_INDEX_URL="$AUTH_INDEX_URL"
export PIP_TRUSTED_HOST="$ART_HOST"
unset PIP_EXTRA_INDEX_URL || true

# Clean old pipenv if present
pipx uninstall pipenv >/dev/null 2>&1 || true

# Install pipenv (verbose for debugging)
PIP_INDEX_URL="$PIP_INDEX_URL" PIP_TRUSTED_HOST="$PIP_TRUSTED_HOST" \
  pipx install --python "$PY312" pipenv -v

echo
echo "pipenv installed:"
pipenv --version
echo

echo "==========[ 5) Create repo venv using Python 3.12 ]=========="
pipenv --rm >/dev/null 2>&1 || true

export PIPENV_PYTHON="$PY312"
# Ensure pipenv also uses Artifactory for resolving deps
export PIP_INDEX_URL="$AUTH_INDEX_URL"
export PIP_TRUSTED_HOST="$ART_HOST"
unset PIP_EXTRA_INDEX_URL || true

pipenv install --dev

echo
echo "Project python:"
pipenv run python --version
echo

echo "==========[ 6) Generate Pipfile.lock ]=========="
pipenv lock --clear

echo
echo "✅ SUCCESS: Pipfile.lock generated with Python 3.12"
echo "Repo: $REPO_DIR"
EOF
chmod +x fix_pipenv_312.sh


///////////////

source ./.env.artifactory
echo "$ART_HOST"
echo "$ART_INDEX_PATH"


////////////////


bash ./fix_pipenv_312.sh

////////////////////////
