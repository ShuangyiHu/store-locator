#!/bin/sh
set -e

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Seeding roles, permissions, services..."
python -m seeds.seed_roles

echo "==> Seeding test users..."
python -m seeds.seed_users

echo "==> Seeding stores (1000 records)..."
python -m seeds.seed_stores data/stores_1000.csv

echo "==> Starting gunicorn..."
exec gunicorn app.main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
