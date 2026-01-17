FROM python:3.12-slim

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System packages often required by Python wheels (cryptography, Pillow, psycopg2 later, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      curl \
      ca-certificates \
      ffmpeg \
      libffi-dev \
      libssl-dev \
      libjpeg62-turbo-dev \
      zlib1g-dev \
      libpq-dev \
      git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip toolchain
RUN python -m pip install --upgrade pip setuptools wheel

# Copy and install Python deps first (better cache)
COPY requirements.txt .
# Prefer prebuilt wheels when possible to avoid compiling from source
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy app source
COPY . .

EXPOSE 8000
