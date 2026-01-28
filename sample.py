# Option B: if your real code is under src/
pipenv run pytest -q --maxfail=1 --disable-warnings \
  --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml
