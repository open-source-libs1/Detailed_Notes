# from the host, in the folder with docker-compose.yml
docker compose exec enrollment-writer sh -lc \
 'cd /app && pipenv run behave tests/component/features --format=json.pretty --outfile=./reports/cucumber.json'
