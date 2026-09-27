#!/bin/sh
set -e

echo "=== [entrypoint.sh] Applying database migrations ==="
python manage.py migrate --noinput

echo "=== [entrypoint.sh] Running seed fixtures ==="
python manage.py seed_fixtures

echo "=== [entrypoint.sh] Starting Django development server ==="
exec python manage.py runserver 0.0.0.0:8000
