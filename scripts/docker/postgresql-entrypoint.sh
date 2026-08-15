#!/bin/sh
set -eu

secret_dir="${ANGMOO_SECRET_DIR:-/run/angmoo-secrets}"
mkdir -p "$secret_dir"
umask 077

create_secret() {
  name="$1"
  target="$secret_dir/$name"
  if [ -L "$target" ]; then
    echo "secret_mismatch" >&2
    exit 78
  fi
  if [ -s "$target" ]; then
    return
  fi
  temporary="$secret_dir/.${name}.$$"
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n' >"$temporary"
  chmod 0444 "$temporary"
  mv "$temporary" "$target"
}

create_secret app_secret
create_secret postgresql_password
create_secret neo4j_password

POSTGRES_PASSWORD="$(cat "$secret_dir/postgresql_password")"
export POSTGRES_PASSWORD

exec docker-entrypoint.sh "$@"
