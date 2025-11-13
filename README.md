# Renter
Main repository

Branching
git checkout main
git pull
git checkout -b feat/<short-name>   # or fix/<short-name>, chore/<short-name>


Naming examples:

feat/listings-crud

fix/ci-ghcr-lowercase

chore/precommit-setup

Run the stack (Docker)
cd infra
docker compose up -d web_build
docker compose up -d api worker nginx
# App: http://localhost:8080
# Health: http://localhost:8080/api/healthz


Stop:

docker compose down

Format, Lint, Test (local)

Backend

cd backend
pre-commit run --all-files          # black + isort + flake8
python manage.py test

Frontend (when real app is added)

cd ../frontend
npm ci || npm install
npm run build

Commit (Conventional Commits)
git add -A
git commit -m "feat(listings): create/edit with S3 presign"
# examples:
# fix(ci): lowercase GHCR image tag
# chore(lint): fix flake8 violations


Amend last commit if commitlint fails:

git commit --amend -m "chore(lint): fix flake8 violations"
git push --force-with-lease

Push & Open PR
git push -u origin feat/<short-name>
# open PR: https://github.com/<ORG>/<REPO>/compare/main...feat/<short-name>


PR checklist:

What/why + test notes

Screenshots for UI

CI must pass:

Backend-tests

Frontend-build

Docker-build

Common Commands

Logs / restart

cd infra
docker compose ps
docker compose logs -f api
docker compose restart api


Migrations

docker compose exec api python manage.py makemigrations
docker compose exec api python manage.py migrate


Run a single test

docker compose exec api pytest backend/tests/test_healthz.py::test_healthz -q

# always start work like this:
git checkout main
git fetch origin
git pull --ff-only
git checkout -b feat/<topic>
# ...work, commit, push, open PR...
# after merge:
git checkout main && git pull --ff-only && git branch -d feat/<topic> && git push origin --delete feat/<topic>