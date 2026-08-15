#!/bin/sh
set -eu

secret_dir="${ANGMOO_SECRET_DIR:-/run/angmoo-secrets}"
attempt=0
while [ ! -s "$secret_dir/app_secret" ] \
  || [ ! -s "$secret_dir/postgresql_password" ] \
  || [ ! -s "$secret_dir/neo4j_password" ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "secret_missing" >&2
    exit 78
  fi
  sleep 1
done

APP_SECRET="$(cat "$secret_dir/app_secret")"
NEO4J_PASSWORD="$(cat "$secret_dir/neo4j_password")"
postgresql_password="$(cat "$secret_dir/postgresql_password")"
database_scheme="postgresql+psycopg"
database_authority="${ANGMOO_POSTGRES_USER:-angmoo}:${postgresql_password}@${ANGMOO_POSTGRES_HOST:-postgresql}:5432"
export APP_SECRET NEO4J_PASSWORD
export DATABASE_URL="${database_scheme}://${database_authority}/${ANGMOO_POSTGRES_DB:-angmoo}"

mode="${1:-api}"
case "$mode" in
  api)
    alembic upgrade head
    exec uvicorn app.public_main:app --host 0.0.0.0 --port 8080
    ;;
  api-dev)
    alembic upgrade head
    exec uvicorn app.public_main:app --host 0.0.0.0 --port 8080 --reload
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  scheduler)
    : > /tmp/angmoo-worker-ready
    exec python scripts/run_resident_tick_scheduler.py
    ;;
  projector)
    : > /tmp/angmoo-worker-ready
    exec python scripts/run_graph_projection_worker.py --loop --bootstrap
    ;;
  *)
    echo "unsupported_runtime_process" >&2
    exit 64
    ;;
esac
