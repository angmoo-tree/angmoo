#!/bin/sh
set -eu

embedded_data_root="${ANGMOO_CONTRIBUTOR_DATA_ROOT:-/var/lib/angmoo}"
embedded_frontend_origin="${ANGMOO_FRONTEND_ORIGIN:-http://127.0.0.1:3000}"

run_as_angmoo() {
  if [ "$(id -u)" = "0" ]; then
    exec setpriv --reuid=10001 --regid=10001 --init-groups -- "$@"
  fi
  exec "$@"
}

prepare_embedded_data_root() {
  if [ "$(id -u)" = "0" ]; then
    install -d -o 10001 -g 10001 -m 0700 "$embedded_data_root"
    for directory in canonical graph search media secrets runtime logs; do
      install -d -o 10001 -g 10001 -m 0700 "$embedded_data_root/$directory"
    done
  elif [ ! -d "$embedded_data_root" ] || [ ! -w "$embedded_data_root" ]; then
    echo "contributor_data_root_unwritable" >&2
    exit 78
  fi
}

mode="${1:-postgresql-api}"
case "$mode" in
  postgresql-installation)
    shift
    run_as_angmoo python -m app.runtime.postgresql_installation "$@"
    ;;
  postgresql-api)
    shift
    # Mount the old volume read-only: replacing the Compose file must never
    # silently open a fresh PostgreSQL database instead of existing user data.
    if [ -d /var/lib/angmoo-legacy/canonical ] && [ ! -f "$embedded_data_root/runtime/postgresql-runtime.json" ]; then
      echo 'sqlite_data_requires_migration: use the documented 0.1.3 migration tool' >&2
      exit 78
    fi
    python -m app.runtime.product_identity
    prepare_embedded_data_root
    if [ ! -f "$embedded_data_root/runtime/postgresql-runtime.json" ]; then
      bootstrap="${ANGMOO_BOOTSTRAP_SECRETS:-/run/angmoo-bootstrap}"
      test -f "$bootstrap/installation-id"
      python -m app.runtime.postgresql_installation initialize \
        --data-root "$embedded_data_root" \
        --installation-id "$(cat "$bootstrap/installation-id")" \
        --owner-dsn-file "$bootstrap/owner-dsn" \
        --runtime-dsn-file "$bootstrap/runtime-dsn"
    fi
    if [ "$(id -u)" = "0" ]; then
      chown -R --no-dereference 10001:10001 "$embedded_data_root"
    fi
    run_as_angmoo python -m app.runtime.postgresql_server \
      --data-root "$embedded_data_root" \
      --host "${ANGMOO_BIND_HOST:-0.0.0.0}" \
      --port "${ANGMOO_BACKEND_PORT:-8080}" \
      --frontend-origin "$embedded_frontend_origin" "$@"
    ;;
  contributor-api|contributor-api-dev)
    shift
    exec "$0" postgresql-api "$@"
    ;;
  contributor-diagnostics)
    run_as_angmoo python -m app.runtime.postgresql_server \
      --data-root "$embedded_data_root" --frontend-origin "$embedded_frontend_origin" --diagnostics
    ;;
  *)
    echo "unsupported_runtime_process" >&2
    exit 64
    ;;
esac
