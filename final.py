# from your host, in the same folder as docker-compose.yml
docker compose exec enrollment-writer bash   # or sh

# now inside the container
cd /app                                      # repo root (adjust if needed)
pipenv run behave tests/component/features \
  --format=json.pretty \
  --outfile=./reports/cucumber.json
