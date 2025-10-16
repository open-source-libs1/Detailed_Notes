cd /path/to/your/repo/lambda \
&& export PATH="$HOME/.local/bin:$PATH" \
&& export PIPENV_VENV_IN_PROJECT=1 \
&& PY312="/opt/homebrew/opt/python@3.12/bin/python3.12" \
&& pipenv --python "$PY312" \
&& (pipenv sync --dev || pipenv install --dev) \
&& pipenv run python -c "import pydantic; print(pydantic.__version__)" \
&& export PYTHONPATH="$PWD/src" \
&& pipenv run pytest -q --cov=src --cov-report=term-missing
