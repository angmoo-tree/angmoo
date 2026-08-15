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

if [ -L "$secret_dir/app_secret" ] \
  || [ ! -f "$secret_dir/app_secret" ] \
  || [ ! -r "$secret_dir/app_secret" ]; then
  echo "secret_volume_unavailable" >&2
  exit 78
fi
app_secret_mode="$(stat -c '%a' "$secret_dir/app_secret")"
if [ "$app_secret_mode" != "400" ]; then
  echo "secret_acl_unsafe secret=app_secret" >&2
  exit 78
fi

APP_SECRET_FILE="$secret_dir/app_secret"
NEO4J_PASSWORD="$(cat "$secret_dir/neo4j_password")"
postgresql_password="$(cat "$secret_dir/postgresql_password")"
database_scheme="postgresql+psycopg"
database_authority="${ANGMOO_POSTGRES_USER:-angmoo}:${postgresql_password}@${ANGMOO_POSTGRES_HOST:-postgresql}:5432"
export APP_SECRET_FILE NEO4J_PASSWORD
export DATABASE_URL="${database_scheme}://${database_authority}/${ANGMOO_POSTGRES_DB:-angmoo}"

prepare_database() {
  alembic upgrade head
  python scripts/migrate_local_credentials.py
}

mode="${1:-api}"
case "$mode" in
  api)
    prepare_database
    exec uvicorn app.public_main:app --host 0.0.0.0 --port 8080
    ;;
  api-dev)
    prepare_database
    exec uvicorn app.public_main:app --host 0.0.0.0 --port 8080 --reload
    ;;
  migrate)
    alembic upgrade head
    exec python scripts/migrate_local_credentials.py
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
