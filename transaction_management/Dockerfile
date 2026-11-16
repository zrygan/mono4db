FROM node:22

WORKDIR /usr/src/app

COPY package*.json ./

RUN npm install --omit=dev && \
    apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client && \
    rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000

CMD [ "node", "server.js"]