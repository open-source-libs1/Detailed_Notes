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



////////////



  export NVM_NODEJS_ORG_MIRROR="https://nodejs.org/dist"
nvm ls-remote | tail -n 20
nvm install 24



/////////////////////


export NVM_NODEJS_ORG_MIRROR="https://nodejs.org/dist"
nvm use 24.14.0
node -v
npm -v
