#!/bin/sh
set -eu

PUID="${PUID:-10001}"
PGID="${PGID:-10001}"

case "$PUID:$PGID" in
  *[!0-9:]* | :* | *:)
    echo "PUID and PGID must be positive numeric IDs." >&2
    exit 1
    ;;
esac

if [ "$PUID" -eq 0 ] || [ "$PGID" -eq 0 ]; then
  echo "PUID and PGID must not be 0." >&2
  exit 1
fi

mkdir -p "${MESHIVE_DATA_DIR:-/app/data}" "${MESHIVE_CACHE_DIR:-/app/cache}" \
  "${MESHIVE_BACKUP_DIR:-/backups}"
chown -R "$PUID:$PGID" \
  "${MESHIVE_DATA_DIR:-/app/data}" \
  "${MESHIVE_CACHE_DIR:-/app/cache}" \
  "${MESHIVE_BACKUP_DIR:-/backups}"

if [ "$#" -gt 0 ]; then
  exec gosu "$PUID:$PGID" "$@"
fi

if [ -f "${MESHIVE_DATA_DIR:-/app/data}/restore-request.json" ]; then
  gosu "$PUID:$PGID" meshive restore-pending
fi

gosu "$PUID:$PGID" alembic -c /app/backend/alembic.ini upgrade head

exec gosu "$PUID:$PGID" uvicorn meshive.main:app --host 0.0.0.0 --port 8000
