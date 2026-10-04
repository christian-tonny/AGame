#!/bin/sh
# Seed an empty data volume with schema-valid empty fixtures, fix ownership, drop privileges.
set -eu
DATA="${AGAME_DATA_DIR:-/data}"
mkdir -p "$DATA"
if [ ! -f "$DATA/profile.json" ]; then
  echo "agame: seeding empty data volume at $DATA"
  cp -n /app/seed-data/* "$DATA"/
fi
if [ "$(id -u)" = "0" ]; then
  chown -R agame:agame "$DATA"
  exec setpriv --reuid=agame --regid=agame --init-groups "$@"
fi
exec "$@"
