
RUN ["npm", "install", "webpack", "webpack-cli", "mini-css-extract-plugin", "--legacy-peer-deps", "--no-audit", "--no-fund"]
RUN ["npm", "install", "--legacy-peer-deps", "--no-audit", "--no-fund"]
RUN ["npm", "run", "build"]
