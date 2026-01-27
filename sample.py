pipenv run pytest --maxfail=1 --disable-warnings -q \
  --cov=app \
  --cov-report=term-missing \
  --cov-report=html \
  --cov-report=xml
