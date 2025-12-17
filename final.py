docker compose exec enrollment-writer sh -lc '
  cd /app \
  && python -m behave tests/component/features --format=json.pretty --outfile=./reports/cucumber.json
'
