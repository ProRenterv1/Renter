Set-Location $PSScriptRoot\..\infra

# Rebuild all images from scratch so containers always start from fresh artifacts
docker compose build --no-cache web_build api worker

# Force recreation so every run gets brand-new containers and regenerated files
docker compose up --force-recreate -d web_build
docker compose up --force-recreate -d api worker nginx
