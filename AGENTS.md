# AGENTS.md

These are repo-specific instructions for coding agents working on Rentino.

## Repo layout
- `backend/`: Django + Celery + Postgres/Redis code.
- `frontend/`: Vite + React + TypeScript UI.
- `infra/`: Docker Compose stack (api/worker/nginx/db/redis/pgbouncer).
- `scripts/`: helper scripts (e.g., `dev-up.ps1`, `dev-down.ps1`).
- Docs: `README.md`, `README-auth.md`, `SPECIAL.md`.

## How to run (preferred)
- Start stack: `pwsh ./scripts/dev-up.ps1`
- Stop stack: `pwsh ./scripts/dev-down.ps1`
- Docker Compose commands run from `infra/`.

## Backend workflow
- Run commands in Docker (preferred):
  - `cd infra && docker compose exec api python manage.py <command>`
- Run tests on host:
  - `cd backend && pytest <path>::<test>`
  - `cd backend && python manage.py test`
- Format/lint:
  - `cd backend && pre-commit run --all-files`
- If a model changes, add a Django migration under the correct app.
- When introducing configurable behavior, prefer `core.settings_resolver` and add defaults in `operator_settings` (including a migration for new defaults).
- Log important booking state changes via `operator_bookings.BookingEvent` when appropriate.

## Frontend workflow
- `cd frontend && npm install`
- `npm run dev` (http://localhost:5173)
- `npm run build` and `npm run preview` for production checks.
- API types live in `frontend/src/lib/api.ts`; update these when backend responses or enums change.

## Data seeding
See `SPECIAL.md` for seed command order and options.

## Troubleshooting
- If `pytest` capture fails with a temp file error, rerun with `--capture=no`.

## General coding notes
- Keep changes minimal and consistent with existing patterns.
- Prefer `rg` for searching.
- Update both backend and frontend enums/types when adding new categories or statuses.
