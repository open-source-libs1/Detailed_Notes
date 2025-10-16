cd /path/to/your/project/fulfillment \
&& export PIPENV_VENV_IN_PROJECT=1 \
&& export PATH="$HOME/.local/bin:$PATH" \
&& PY312="/opt/homebrew/opt/python@3.12/bin/python3.12" \
&& ~/.local/bin/pipenv --python "$PY312" \
&& (~/.local/bin/pipenv sync --dev || ~/.local/bin/pipenv install --dev) \
&& ~/.local/bin/pipenv run pytest -q --cov=src --cov-report=term-missing
