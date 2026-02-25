
echo "len=$(printf %s "$NPM_TOKEN" | wc -c | tr -d ' ')"
printf "%s" "$NPM_TOKEN" | docker build --no-cache --progress=plain --secret id=npm_token,src=/dev/stdin -t f1000-docker .
