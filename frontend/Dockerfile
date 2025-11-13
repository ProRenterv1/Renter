FROM node:20-alpine
WORKDIR /app
COPY package*.json ./

RUN npm install -g npm@11.6.2 \
    && npm ci --include=optional
COPY . .
RUN npm run build