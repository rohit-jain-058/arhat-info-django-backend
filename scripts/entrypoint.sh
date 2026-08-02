#!/bin/sh
set -e

echo "==> Waiting for database..."
while ! nc -z "$DB_HOST" "${DB_PORT:-5432}"; do
  sleep 0.5
done
echo "==> Database is ready."

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "==> Starting server..."
exec "$@"
