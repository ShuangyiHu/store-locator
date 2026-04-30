#!/bin/sh
set -e

# Render provides postgres:// but psycopg2 requires postgresql://
if echo "$DATABASE_URL" | grep -q "^postgres://"; then
  export DATABASE_URL="postgresql://${DATABASE_URL#postgres://}"
  echo "==> Rewrote DATABASE_URL prefix: postgres:// → postgresql://"
fi

echo "==> Running database migrations..."
alembic upgrade head

if [ "$ENVIRONMENT" = "development" ]; then
  echo "==> Seeding dev data..."
  python -m seeds.seed_roles
  python -m seeds.seed_users
  python -m seeds.seed_stores data/stores_1000.csv
fi


echo "==> Starting gunicorn..."
exec gunicorn app.main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
