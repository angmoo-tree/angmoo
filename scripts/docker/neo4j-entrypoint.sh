#!/bin/sh
set -eu

secret_file="${ANGMOO_SECRET_DIR:-/run/angmoo-secrets}/neo4j_password"
attempt=0
while [ ! -s "$secret_file" ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "secret_missing" >&2
    exit 78
  fi
  sleep 1
done

NEO4J_AUTH="neo4j/$(cat "$secret_file")"
export NEO4J_AUTH

exec /startup/docker-entrypoint.sh "$@"
