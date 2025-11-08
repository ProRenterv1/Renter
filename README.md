# Renter
Main repository

Useful commands:
# Stop stack
docker compose down

# See logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f nginx

# Rebuild BE only after code changes
docker compose build api; docker compose up -d api

# Run Django migrations inside the container
docker compose exec api python manage.py migrate

# Open a Django shell inside the container
docker compose exec api python manage.py shell