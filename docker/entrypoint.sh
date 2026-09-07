#!/bin/sh
set -eu

PUID="${PUID:-10001}"
PGID="${PGID:-10001}"
DATA_DIR="${MESHIVE_DATA_DIR:-/app/data}"
CACHE_DIR="${MESHIVE_CACHE_DIR:-/app/cache}"
BACKUP_DIR="${MESHIVE_BACKUP_DIR:-/backups}"
ALEMBIC_CONFIG="${MESHIVE_ALEMBIC_CONFIG:-/app/backend/alembic.ini}"

. /app/permissions.sh
validate_runtime_identity
prepare_runtime_dirs "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"

if [ "$#" -gt 0 ]; then
  exec gosu "$PUID:$PGID" "$@"
fi

if [ -f "$DATA_DIR/restore-request.json" ]; then
  gosu "$PUID:$PGID" meshive restore-pending
fi

gosu "$PUID:$PGID" alembic -c "$ALEMBIC_CONFIG" upgrade head

exec gosu "$PUID:$PGID" uvicorn meshive.main:app --host 0.0.0.0 --port 8000
