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

mode="${1:-contributor-api}"
case "$mode" in
  contributor-api|contributor-api-dev)
    prepare_embedded_data_root
    reload_argument=""
    if [ "$mode" = "contributor-api-dev" ]; then
      reload_argument="--reload"
    fi
    # shellcheck disable=SC2086
    run_as_angmoo python -m app.runtime.contributor_backend \
      --data-root "$embedded_data_root" \
      --host 0.0.0.0 \
      --port 8080 \
      --frontend-origin "$embedded_frontend_origin" \
      $reload_argument
    ;;
  contributor-diagnostics)
    prepare_embedded_data_root
    run_as_angmoo python -m app.runtime.contributor_backend \
      --data-root "$embedded_data_root" \
      --frontend-origin "$embedded_frontend_origin" \
      --diagnostics
    ;;
  *)
    echo "unsupported_runtime_process" >&2
    exit 64
    ;;
esac
