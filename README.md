# Renter

Full-stack renter experience built with Django, Celery, Postgres, Redis, and a Vite/React frontend. This document captures the day-to-day workflow, how to operate the Dockerized stack, and the team's git conventions.

## Contents
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Daily Workflow](#daily-workflow)
- [Working With Containers](#working-with-containers)
- [Backend Development](#backend-development)
- [Object Storage (S3/R2)](#object-storage-s3r2)
- [Frontend Development](#frontend-development)
- [Git & Branching Conventions](#git--branching-conventions)
- [After Your PR Merges](#after-your-pr-merges)
- [Useful One-Liners](#useful-one-liners)

## Prerequisites
- Docker Desktop 4.x (Docker Compose v2 included)
- PowerShell 7+ (`pwsh`) or Windows PowerShell (for the provided scripts)
- Python 3.11+ (only needed if you run Django locally outside of Docker)
- Node.js 20+ and npm 10+ (for local frontend development)

## Quick Start
All commands below are run from the repository root unless noted otherwise.

1. **Bring everything up**
   ```powershell
   pwsh ./scripts/dev-up.ps1
   ```
   The script rebuilds images (`web_build`, `api`, `worker`), then recreates db/redis/app containers under `infra/`.

2. **Access the app**
   - App: http://localhost:8080
   - Health: http://localhost:8080/api/healthz

3. **Shut everything down**
   ```powershell
   pwsh ./scripts/dev-down.ps1
   ```
   (Equivalent to running `docker compose down` inside `infra/`.)

## Daily Workflow
- **Start your day**
  ```bash
  git checkout main
  git fetch origin
  git pull --ff-only
  git checkout -b feat/<topic>   # or fix/<topic>, chore/<topic>
  ```
- **Sync frequently** to avoid drift: `git fetch origin && git pull --ff-only`.
- **Parking work?** Commit locally, push to origin, and leave a short note in the PR description if needed.

## Working With Containers
All Docker commands run from `infra/`.

- **Status & health**
  ```bash
  docker compose ps
  docker compose logs --tail=100 api
  docker compose logs -f api   # follow logs
  docker compose restart api   # restart a single service
  ```
- **Database & cache**
  Containers `db` and `redis` start automatically via `dev-up`. Use `docker compose exec db psql ...` for manual DB access.
- **Stop / cleanup**
  ```bash
  docker compose down           # stop containers
  docker compose down -v        # stop and drop volumes (only if you need a clean DB)
  ```

## Backend Development
- **Open a Django shell / run management commands**
  ```bash
  docker compose exec api python manage.py shell
  docker compose exec api python manage.py createsuperuser
  ```
- **Migrations inside the container**
  ```bash
  docker compose exec api python manage.py makemigrations
  docker compose exec api python manage.py migrate
  ```
- **Celery worker logs**
  ```bash
  docker compose logs -f worker
  ```
- **Tests & linters (on the host)**
  ```bash
  cd backend
  pre-commit run --all-files    # black + isort + flake8, etc.
  python manage.py test
  ```
- **Tests inside Docker**
  ```bash
  cd infra
  docker compose exec api pytest backend/users/tests/test_login_events_api.py::test_login_events_list -q
  ```

## Object Storage (S3/R2)
- Set `USE_S3=true` and supply `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (R2 access keys work); bucket lives in `AWS_STORAGE_BUCKET_NAME`.
- For R2, prefer `R2_ACCOUNT_ID` (or set `AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`), keep `AWS_S3_REGION_NAME=auto`, and leave `AWS_S3_FORCE_PATH_STYLE=true`.
- Public URLs are built from `S3_PUBLIC_BASE_URL` first (set to your `https://<bucket>.r2.dev` or custom domain), then `MEDIA_BASE_URL`, then the endpoint/bucket fallback.
- Upload prefixes stay under `S3_UPLOADS_PREFIX` (default `uploads/listings`); presign flows remain compatible with AWS-style clients.
- Cutover checklist: create the R2 bucket + access keys, configure `*.r2.dev` or a custom domain, copy existing objects (e.g., `aws s3 sync --endpoint-url https://<account-id>.r2.cloudflarestorage.com s3://old-bucket s3://new-bucket`), deploy with the new env vars, and smoke-test uploads/AV tagging.

## Frontend Development
Run the frontend separately when iterating quickly on UI:

```bash
cd frontend
npm install           # or npm ci
npm run dev           # Vite dev server on http://localhost:5173
```

- Environment variables are managed via `.env` files understood by Vite (see `frontend/.env.example` if present).
- For production builds: `npm run build` then `npm run preview` to smoke-test the output.

## Git & Branching Conventions
- **Branch naming**
  - `feat/<short-topic>` for new work (e.g., `feat/listings-crud`)
  - `fix/<short-topic>` for bug fixes (e.g., `fix/login-analytics`)
  - `chore/<short-topic>` for upkeep (e.g., `chore/precommit-setup`)
- **Creating a branch**
  ```bash
  git checkout -b feat/<short-topic>
  ```
- **Commit messages**
  Follow Conventional Commits: `type(scope): summary`
  - `feat(listings): add CRUD endpoints`
  - `fix(ci): lowercase GHCR image tag`
  - `chore(lint): fix flake8 violations`
- **If commit lint fails**
  ```bash
  git commit --amend
  git push --force-with-lease
  ```
- **Push & open a PR**
  ```bash
  git push -u origin feat/<short-topic>
  ```
  Then open `https://github.com/<ORG>/<REPO>/compare/main...feat/<short-topic>` and fill in:
  - What/why summary
  - Test notes & screenshots (if UI)
  - Confirm CI checks: backend-tests, frontend-build, docker-build

## After Your PR Merges
```bash
git checkout main
git pull --ff-only
git branch -d feat/<short-topic>
git push origin --delete feat/<short-topic>
```
Finally, run `pwsh ./scripts/dev-up.ps1` again if the stack needs updated images/data after the merge.

## Useful One-Liners
- **Tail a specific service**
  ```bash
  cd infra && docker compose logs -f nginx
  ```
- **Re-run the stack with fresh artifacts**
  ```bash
  pwsh ./scripts/dev-up.ps1
  ```
- **Run a focused test in Docker**
  ```bash
  cd infra && docker compose exec api pytest backend/tests/test_healthz.py::test_healthz -q
  ```
- **Cleanup dangling Docker resources**
  ```bash
  docker system prune
  ```

Refer back to this README whenever you need the canonical workflow for spinning up services, working inside containers, or following the team's git process.
