FROM node:20-alpine
WORKDIR /app

# Build-time toggle for ops bundle (default off for public build)
ARG VITE_OPS_BUILD=0
ENV VITE_OPS_BUILD=${VITE_OPS_BUILD}
ARG VITE_GOOGLE_OAUTH_CLIENT_ID
ENV VITE_GOOGLE_OAUTH_CLIENT_ID=${VITE_GOOGLE_OAUTH_CLIENT_ID}
ARG VITE_STRIPE_PUBLISHABLE_KEY
ENV VITE_STRIPE_PUBLISHABLE_KEY=${VITE_STRIPE_PUBLISHABLE_KEY}

COPY package*.json ./
RUN set -e; \
    npm config set fetch-retries 5; \
    npm config set fetch-retry-mintimeout 20000; \
    npm config set fetch-retry-maxtimeout 120000; \
    npm config set fund false; \
    npm config set audit false; \
    for attempt in 1 2 3; do \
      if npm install -g npm@11.6.2 && npm ci --include=optional; then \
        break; \
      fi; \
      if [ "$attempt" -eq 3 ]; then \
        exit 1; \
      fi; \
      sleep $((attempt * 5)); \
    done

COPY . .
RUN npm run build
