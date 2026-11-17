# --- build stage: compile TypeScript ---
FROM node:22 AS build
WORKDIR /usr/src/app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# --- runtime stage: production deps + compiled JS only ---
FROM node:22
WORKDIR /usr/src/app
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client && \
    rm -rf /var/lib/apt/lists/*
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=build /usr/src/app/dist ./dist
COPY src/app/public ./dist/app/public
EXPOSE 8000
CMD ["node", "dist/server.js"]
