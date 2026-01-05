FROM node:20-alpine
WORKDIR /app

# Build-time toggle for ops bundle (default off for public build)
ARG VITE_OPS_BUILD=0
ENV VITE_OPS_BUILD=${VITE_OPS_BUILD}
ARG VITE_GOOGLE_OAUTH_CLIENT_ID
ENV VITE_GOOGLE_OAUTH_CLIENT_ID=${VITE_GOOGLE_OAUTH_CLIENT_ID}

COPY package*.json ./
RUN npm install -g npm@11.6.2 \
    && npm ci --include=optional

COPY . .
RUN npm run build
