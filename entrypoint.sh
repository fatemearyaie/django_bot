#!/bin/sh
set -e

export PGPASSWORD="${POSTGRES_PASSWORD}"

# Wait for Postgres on host
until psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c '\q' >/dev/null 2>&1; do
  echo "Waiting for Postgres..."
  sleep 2
done

echo "Postgres is ready."

if [ "${RUN_MIGRATIONS}" = "1" ]; then
  echo "Running migrations..."
  python manage.py makemigrations
  python manage.py migrate --noinput
  python manage.py createcachetable || true
fi

exec "$@"
