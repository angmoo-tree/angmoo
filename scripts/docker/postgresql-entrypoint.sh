#!/bin/sh
set -eu

secret_dir="${ANGMOO_SECRET_DIR:-/run/angmoo-secrets}"
data_dir="${PGDATA:-/var/lib/postgresql/data}"
if ! mkdir -p "$secret_dir" || [ ! -w "$secret_dir" ]; then
  echo "secret_volume_unavailable" >&2
  exit 78
fi
umask 077

set_secret_permissions() {
  name="$1"
  target="$secret_dir/$name"
  if [ "$name" = "app_secret" ]; then
    if ! chown 10001:10001 "$target" || ! chmod 0400 "$target"; then
      echo "secret_acl_unsafe secret=app_secret" >&2
      exit 78
    fi
  elif ! chmod 0444 "$target"; then
    echo "secret_acl_unsafe secret=$name" >&2
    exit 78
  fi
}

fail_missing_secret() {
  name="$1"
  if [ "$name" = "app_secret" ]; then
    echo "credential_recovery_required secret=app_secret" >&2
  else
    echo "secret_recovery_required secret=$name" >&2
  fi
  exit 78
}

validate_secret() {
  name="$1"
  target="$secret_dir/$name"
  if [ -L "$target" ]; then
    echo "secret_mismatch secret=$name" >&2
    exit 78
  fi
  if [ ! -f "$target" ] || [ ! -s "$target" ]; then
    fail_missing_secret "$name"
  fi
  set_secret_permissions "$name"
}

create_secret() {
  name="$1"
  target="$secret_dir/$name"
  if [ -L "$target" ]; then
    echo "secret_mismatch secret=$name" >&2
    exit 78
  fi
  if [ -s "$target" ]; then
    set_secret_permissions "$name"
    return
  fi
  temporary="$secret_dir/.${name}.$$"
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n' >"$temporary"
  chmod 0600 "$temporary"
  mv "$temporary" "$target"
  set_secret_permissions "$name"
}

if [ -s "$data_dir/PG_VERSION" ]; then
  validate_secret app_secret
  validate_secret postgresql_password
  validate_secret neo4j_password
else
  create_secret app_secret
  create_secret postgresql_password
  create_secret neo4j_password
fi

POSTGRES_PASSWORD="$(cat "$secret_dir/postgresql_password")"
export POSTGRES_PASSWORD

exec docker-entrypoint.sh "$@"
