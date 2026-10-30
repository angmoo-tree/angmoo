#!/bin/sh
set -eu
if [ "${ANGMOO_BOOTSTRAP_SECRETS:-}" != "" ]; then
  directory="$ANGMOO_BOOTSTRAP_SECRETS"
  if [ -f "${PGDATA:-/var/lib/postgresql/data}/PG_VERSION" ]; then
    for name in installation-id postgres-password owner-dsn runtime-dsn; do
      if [ ! -f "$directory/$name" ] || [ -L "$directory/$name" ]; then
        echo 'postgresql_bootstrap_credentials_missing: restore the matching secret volume' >&2
        exit 78
      fi
    done
  fi
  umask 077
  mkdir -p "$directory"
  chmod 0700 "$directory"
  if [ ! -f "$directory/installation-id" ]; then
    test ! -f "$directory/owner-dsn"
    owner=$(od -An -N48 -tx1 /dev/urandom | tr -d ' \n')
    runtime=$(od -An -N48 -tx1 /dev/urandom | tr -d ' \n')
    identifier=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
    printf '%s\n' "$owner" > "$directory/postgres-password"
    printf 'postgresql+psycopg://angmoo_owner:%s@postgres:5432/angmoo\n' "$owner" > "$directory/owner-dsn"
    printf 'postgresql+psycopg://angmoo_runtime:%s@postgres:5432/angmoo\n' "$runtime" > "$directory/runtime-dsn"
    printf 'angmoo-%s\n' "$identifier" > "$directory/installation-id"
  fi
  if [ "$(id -u)" = 0 ]; then
    chown -R postgres:postgres "$directory"
  fi
  export POSTGRES_PASSWORD_FILE="$directory/postgres-password"
fi
exec /usr/local/bin/docker-entrypoint.sh "$@"
