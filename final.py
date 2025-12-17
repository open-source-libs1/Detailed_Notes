docker compose exec enrollment-writer sh -lc '
  cd /app \
  && mkdir -p reports \
  && behave tests/component/features --format=json.pretty --outfile=./reports/cucumber.json
'
