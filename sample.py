WORKDIR /src

COPY . /src

RUN echo "current directory: $PWD"
RUN ls

# >>> ADD THESE TWO DEBUG LINES RIGHT HERE <<<
RUN node -v && npm -v
RUN npm config get registry && npm config list

# existing lines (leave as-is)
RUN npm install
RUN echo "yes" | npm install --production
