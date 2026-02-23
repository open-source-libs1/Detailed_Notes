cat > fix_pipenv_312.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(pwd)"
PY312="/opt/homebrew/bin/python3.12"
ART_HOST="artifactory.cloud.capitalone.com"
ART_INDEX_PATH="/artifactory/api/pypi/pypi-internalfacing/simple"
ART_BASE="https://${ART_HOST}${ART_INDEX_PATH}"

echo "==========[ 0) Context ]=========="
echo "Repo: ${REPO_DIR}"
echo "Python 3.12 expected at: ${PY312}"
echo "Artifactory (internalfacing): ${ART_BASE}"
echo

echo "==========[ 1) Verify Python 3.12 ]=========="
if [[ ! -x "${PY312}" ]]; then
  echo "ERROR: ${PY312} not found."
  echo "Run: brew install python@3.12"
  exit 1
fi
"${PY312}" --version
echo

echo "==========[ 2) Read Pipfile source URL ]=========="
if [[ -f "${REPO_DIR}/Pipfile" ]]; then
  echo "Pipfile exists. First [[source]] url line:"
  grep -n 'url *= *"' Pipfile | head -n 1 || true
else
  echo "ERROR: Pipfile not found in repo root."
  exit 1
fi
echo

echo "==========[ 3) Configure index URL (anonymous by default) ]=========="
# Anonymous attempt first (no creds)
export PIP_INDEX_URL="${ART_BASE}"
export PIP_TRUSTED_HOST="${ART_HOST}"
unset PIP_EXTRA_INDEX_URL || true

echo "PIP_INDEX_URL set to (no creds): ${PIP_INDEX_URL}"
echo

echo "==========[ 4) Ensure pipx exists ]=========="
if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx not found. Installing via brew..."
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: brew not found. Install Homebrew or install pipx another way."
    exit 1
  fi
  brew install pipx
  pipx ensurepath || true
  export PATH="$HOME/.local/bin:$PATH"
fi
pipx --version
echo

echo "==========[ 5) Debug: Can we reach Artifactory index quickly? ]=========="
# Use curl to avoid pip's PEP668 checks and to test auth requirement
# We check the simple index root (should return HTML or 401/403)
set +e
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${ART_BASE}/")"
set -e
echo "HTTP status for ${ART_BASE}/ : ${HTTP_CODE}"
if [[ "${HTTP_CODE}" == "401" || "${HTTP_CODE}" == "403" ]]; then
  echo
  echo "Artifactory requires authentication."
  echo "Re-run this script with ART_USER and ART_TOKEN exported, like:"
  echo '  export ART_USER="your_username"'
  echo '  export ART_TOKEN="your_token"'
  echo "  ./fix_pipenv_312.sh"
  echo
  exit 2
fi
echo

echo "==========[ 6) If creds are provided, switch to authenticated URL ]=========="
# If user provided ART_USER + ART_TOKEN, use them
if [[ -n "${ART_USER:-}" && -n "${ART_TOKEN:-}" ]]; then
  export PIP_INDEX_URL="https://${ART_USER}:${ART_TOKEN}@${ART_HOST}${ART_INDEX_PATH}"
  export PIP_TRUSTED_HOST="${ART_HOST}"
  unset PIP_EXTRA_INDEX_URL || true
  echo "Using authenticated PIP_INDEX_URL (masked)."
  echo "${PIP_INDEX_URL}" | sed -E 's#(https://)[^@]+@#\\1***:***@#'
  echo
fi

echo "==========[ 7) Install pipenv via pipx using Python 3.12 ]=========="
# Remove broken/old pipenv if any
pipx uninstall pipenv >/dev/null 2>&1 || true

# Force env vars into pipx invocation to ensure pip inside pipx venv uses them
PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
  pipx install --python "${PY312}" pipenv -v

echo
echo "pipenv installed:"
pipenv --version
echo

echo "==========[ 8) Repo venv: force Python 3.12, install + lock ]=========="
cd "${REPO_DIR}"

# Remove any existing project venv
pipenv --rm >/dev/null 2>&1 || true

# IMPORTANT: force interpreter for the project
export PIPENV_PYTHON="${PY312}"

echo "Creating venv + installing dev deps..."
pipenv install --dev

echo
echo "Verify project interpreter:"
pipenv --py
pipenv run python --version
echo

echo "Generating Pipfile.lock..."
pipenv lock --clear
echo
echo "✅ SUCCESS: Pipfile.lock generated with Python 3.12"
echo

echo "==========[ 9) Optional quick validation of urllib3 pin ]=========="
echo "Pipfile urllib3 line:"
grep -n '^urllib3' Pipfile || true
echo
echo "If lock fails later with urllib3==2.6.3 not found, then that version is not in Artifactory."
echo "You can test availability with:"
echo "  ${PY312} -m venv /tmp/u3 && source /tmp/u3/bin/activate && \\"
echo "  pip install -i \"${ART_BASE}\" --trusted-host \"${ART_HOST}\" \"urllib3==2.6.3\" -v"
echo
EOF
chmod +x fix_pipenv_312.sh




/////////////////



unset HISTFILE
export ART_USER="YOUR_USERNAME"
export ART_TOKEN="YOUR_TOKEN"
./fix_pipenv_312.sh
