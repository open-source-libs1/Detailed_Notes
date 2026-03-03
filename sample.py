# show what shell + node tooling you’re using
which node || true
node -v || true
npm -v || true

command -v nvm || echo "nvm not loaded in this shell"
nvm --version || true

# this is critical in your repo (your startup.sh sets it)
echo "NVM_NODEJS_ORG_MIRROR=$NVM_NODEJS_ORG_MIRROR"
echo "HTTP_PROXY=$HTTP_PROXY"
echo "HTTPS_PROXY=$HTTPS_PROXY"
echo "NO_PROXY=$NO_PROXY"
