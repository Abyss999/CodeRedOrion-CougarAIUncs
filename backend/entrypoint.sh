#!/bin/sh
# Apply pending migrations, then start gunicorn. `db upgrade` is idempotent,
# so container restarts are safe. Retry briefly in case the DB is not accepting
# connections yet (compose already waits for the db healthcheck).
set -e

attempts=0
until flask --app wsgi db upgrade; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge 10 ]; then
    echo "entrypoint: db upgrade failed after $attempts attempts" >&2
    exit 1
  fi
  echo "entrypoint: db upgrade failed (attempt $attempts), retrying in 3s..." >&2
  sleep 3
done

exec gunicorn -b 0.0.0.0:5055 wsgi:app
