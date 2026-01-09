$repoRoot = Resolve-Path "$PSScriptRoot\.."
$frontendEnvPath = Join-Path $repoRoot "frontend\.env"
if (Test-Path $frontendEnvPath) {
  $googleLine = Get-Content $frontendEnvPath |
    Where-Object { $_ -match "^\s*VITE_GOOGLE_OAUTH_CLIENT_ID\s*=" } |
    Select-Object -First 1
  if ($googleLine) {
    $googleValue = ($googleLine -split "=", 2)[1].Trim().Trim("'").Trim('"')
    if ($googleValue) {
      $env:VITE_GOOGLE_OAUTH_CLIENT_ID = $googleValue
    }
  }
}

Set-Location $repoRoot\infra

# Rebuild all images from scratch so containers always start from fresh artifacts
docker compose build --no-cache web_build web_build_ops api worker beat

# Force recreation so every run gets brand-new containers and regenerated files
docker compose up --force-recreate -d db pgbouncer redis
docker compose up --force-recreate -d web_build web_build_ops
docker compose up --force-recreate -d api worker beat nginx nginx_ops
