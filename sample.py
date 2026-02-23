# 1) Confirm you're in the repo
pwd

# 2) Make sure no venv is active (optional)
deactivate 2>/dev/null || true

# 3) Remove any existing pipenv env (you already did, but safe)
pipenv --rm 2>/dev/null || true

# 4) Create a NEW pipenv env using python 3.12 explicitly
PIPENV_PYTHON=python3.12 pipenv install --dev

# 5) Now generate lock
PIPENV_PYTHON=python3.12 pipenv lock --clear
