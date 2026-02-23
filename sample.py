export PIP_INDEX_URL="https://artifactory.cloud.capitalone.com/artifactory/api/pypi/pypi-internalfacing/simple"
export PIP_TRUSTED_HOST="artifactory.cloud.capitalone.com"
unset PIP_EXTRA_INDEX_URL


pipx uninstall pipenv 2>/dev/null || true
pipx install --python /opt/homebrew/bin/python3.12 pipenv -v


pipenv --version


cd /Users/rcw839/Desktop/Projects/2026/FEB/bank-offers-detail-synchronization

pipenv --rm 2>/dev/null || true

PIPENV_PYTHON=/opt/homebrew/bin/python3.12 pipenv install --dev
PIPENV_PYTHON=/opt/homebrew/bin/python3.12 pipenv lock --clear

pipenv run python --version
