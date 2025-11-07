curl -k -X POST "https://api-it.cloud.capitalone.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=" \
  --data-urlencode "client_secret="
