Set-Location $PSScriptRoot\..\infra
docker compose build web_build
docker compose up -d web_build
docker compose up -d api worker nginx
