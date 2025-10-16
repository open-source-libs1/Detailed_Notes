


# from your project folder (where Pipfile is)
export PIPENV_VENV_IN_PROJECT=1

# Option A — simplest (user install)
python3.12 -m pip install --user pipenv
export PATH="$HOME/Library/Python/3.12/bin:$PATH"   # make pipenv visible

# (or Option B — pipx, equally good)
# brew install pipx
# pipx ensurepath
# pipx install pipenv
