set -e

# ----------------------------
# Step 0: basic checks
# ----------------------------
python3.12 --version

# ----------------------------
# Step 1: Point pip/pipx at Artifactory (IMPORTANT)
# ----------------------------
export PIP_INDEX_URL="https://artifactory.cloud.capitalone.com/artifactory/api/pypi/pypi-internal/simple"
export PIP_TRUSTED_HOST="artifactory.cloud.capitalone.com"

# If your Artifactory needs auth, set these (uncomment and fill):
# export PIP_INDEX_URL="https://<user>:<token>@artifactory.cloud.capitalone.com/artifactory/api/pypi/pypi-internal/simple"

# ----------------------------
# Step 2: Ensure pipx exists
# ----------------------------
if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx not found. Installing via brew..."
  brew install pipx
  pipx ensurepath
  export PATH="$HOME/.local/bin:$PATH"
fi

# ----------------------------
# Step 3: Install pipenv using pipx with Python 3.12
# (pipenv was removed earlier, so we re-add it)
# ----------------------------
if pipx list | grep -q "pipenv"; then
  echo "pipenv already installed in pipx; upgrading/reinstalling with python3.12..."
  pipx reinstall --python python3.12 pipenv || true
  pipx upgrade pipenv || true
else
  echo "Installing pipenv with python3.12..."
  pipx install --python python3.12 pipenv
fi

# ----------------------------
# Step 4: Verify pipenv is back
# ----------------------------
pipenv --version

# ----------------------------
# Step 5: Go to repo (edit if your path differs)
# ----------------------------
cd "/Users/rcw839/Desktop/Projects/2026/FEB/bank-offers-detail-synchronization"
pwd

# ----------------------------
# Step 6: Force the project venv to use Python 3.12 and generate lock
# ----------------------------
pipenv --rm 2>/dev/null || true

# Create env + install deps (dev included)
PIPENV_PYTHON=python3.12 pipenv install --dev

# Confirm interpreter
pipenv --py
pipenv run python --version

# Generate lock file
PIPENV_PYTHON=python3.12 pipenv lock --clear

echo "✅ Done: Pipfile.lock generated using Python 3.12"
