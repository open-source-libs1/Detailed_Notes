#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Goal:
# 1) Re-install pipenv (you currently have: zsh: command not found: pipenv)
# 2) Force the project to use Python 3.12
# 3) Generate Pipfile.lock successfully
#
# NOTE: This assumes your corporate PyPI/Artifactory is:
# https://artifactory.cloud.capitalone.com/artifactory/api/pypi/pypi-internal/simple
###############################################################################

echo "==> Step 0: Confirm Python 3.12 exists"
python3.12 --version

echo "==> Step 1: Configure pip to use Artifactory (for THIS terminal session)"
export PIP_INDEX_URL="https://artifactory.cloud.capitalone.com/artifactory/api/pypi/pypi-internal/simple"
export PIP_TRUSTED_HOST="artifactory.cloud.capitalone.com"

echo "==> Step 2: Install pipenv for your user (no pipx needed)"
python3.12 -m pip install --user --upgrade pip
python3.12 -m pip install --user pipenv

echo "==> Step 3: Ensure your shell PATH can find user-installed pipenv"
# macOS user-site bin for Python 3.12:
export PATH="$HOME/Library/Python/3.12/bin:$PATH"

echo "==> Step 4: Verify pipenv is available now"
pipenv --version

echo "==> Step 5: Move to repo root (update this if needed)"
# If you're already in the repo, this will do nothing.
# Otherwise, edit this path.
cd "/Users/rcw839/Desktop/Projects/2026/FEB/bank-offers-detail-synchronization"
pwd

echo "==> Step 6: Remove any existing pipenv virtualenv for this project (safe if none)"
pipenv --rm 2>/dev/null || true

echo "==> Step 7: Create project venv using Python 3.12 and install dependencies"
PIPENV_PYTHON=python3.12 pipenv install --dev

echo "==> Step 8: Confirm the project interpreter is Python 3.12"
pipenv --py
pipenv run python --version

echo "==> Step 9: Generate lock file"
PIPENV_PYTHON=python3.12 pipenv lock --clear

echo "✅ Done: Pipfile.lock generated using Python 3.12"
