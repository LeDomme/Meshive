#!/bin/sh
set -eu

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
MOCK_BIN="$ROOT/mock-bin"
mkdir -p "$MOCK_BIN"

cat > "$MOCK_BIN/stat" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$MESHIVE_TEST_STAT_LOG"
printf '%s\n' "$MESHIVE_TEST_STAT_OWNER"
EOF
cat > "$MOCK_BIN/chown" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$MESHIVE_TEST_CHOWN_LOG"
[ "${MESHIVE_TEST_CHOWN_FAIL:-0}" -ne 1 ]
EOF
chmod 0755 "$MOCK_BIN/stat" "$MOCK_BIN/chown"

PATH="$MOCK_BIN:$PATH"
export PATH
PUID=501
PGID=100
export PUID PGID
. docker/permissions.sh

PUID='501:100'
if validate_runtime_identity; then
    echo "Expected invalid PUID rejection" >&2
    exit 1
fi
PUID=501
PGID=0
if validate_runtime_identity; then
    echo "Expected zero PGID rejection" >&2
    exit 1
fi
PGID=100

reset_logs() {
    : > "$MESHIVE_TEST_STAT_LOG"
    : > "$MESHIVE_TEST_CHOWN_LOG"
}

assert_empty() {
    [ ! -s "$1" ] || {
        echo "Expected $1 to be empty" >&2
        exit 1
    }
}

new_dirs() {
    TEST_DIR="$ROOT/$1"
    DATA_DIR="$TEST_DIR/data"
    CACHE_DIR="$TEST_DIR/cache"
    BACKUP_DIR="$TEST_DIR/backups"
    mkdir -p "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"
}

MESHIVE_TEST_STAT_LOG="$ROOT/stat.log"
MESHIVE_TEST_CHOWN_LOG="$ROOT/chown.log"
export MESHIVE_TEST_STAT_LOG MESHIVE_TEST_CHOWN_LOG

new_dirs correct
MESHIVE_TEST_STAT_OWNER=501:100
export MESHIVE_TEST_STAT_OWNER
MESHIVE_FIX_PERMISSIONS=auto
reset_logs
prepare_runtime_dirs "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"
assert_empty "$MESHIVE_TEST_CHOWN_LOG"
[ "$(wc -l < "$MESHIVE_TEST_STAT_LOG")" -eq 3 ]

new_dirs wrong-root
MESHIVE_TEST_STAT_OWNER=0:0
MESHIVE_FIX_PERMISSIONS=auto
reset_logs
prepare_runtime_dirs "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"
[ "$(wc -l < "$MESHIVE_TEST_CHOWN_LOG")" -eq 3 ]
! grep -q -- '-R' "$MESHIVE_TEST_CHOWN_LOG"

new_dirs failed-chown
MESHIVE_TEST_CHOWN_FAIL=1
export MESHIVE_TEST_CHOWN_FAIL
MESHIVE_FIX_PERMISSIONS=auto
reset_logs
if prepare_runtime_dirs "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"; then
    echo "Expected ownership failure" >&2
    exit 1
fi
[ "$(wc -l < "$MESHIVE_TEST_CHOWN_LOG")" -eq 1 ]
MESHIVE_TEST_CHOWN_FAIL=0
export MESHIVE_TEST_CHOWN_FAIL

new_dirs always
MESHIVE_FIX_PERMISSIONS=always
reset_logs
prepare_runtime_dirs "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"
[ "$(wc -l < "$MESHIVE_TEST_CHOWN_LOG")" -eq 3 ]
grep -q -- "-R 501:100 $DATA_DIR" "$MESHIVE_TEST_CHOWN_LOG"
grep -q -- "-R 501:100 $CACHE_DIR" "$MESHIVE_TEST_CHOWN_LOG"
grep -q -- "-R 501:100 $BACKUP_DIR" "$MESHIVE_TEST_CHOWN_LOG"

new_dirs never
MESHIVE_FIX_PERMISSIONS=never
reset_logs
prepare_runtime_dirs "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"
assert_empty "$MESHIVE_TEST_CHOWN_LOG"
assert_empty "$MESHIVE_TEST_STAT_LOG"

new_dirs large-cache
for index in $(seq 1 500); do
    : > "$CACHE_DIR/$index"
done
MESHIVE_TEST_STAT_OWNER=501:100
MESHIVE_FIX_PERMISSIONS=auto
reset_logs
prepare_runtime_dirs "$DATA_DIR" "$CACHE_DIR" "$BACKUP_DIR"
assert_empty "$MESHIVE_TEST_CHOWN_LOG"
[ "$(wc -l < "$MESHIVE_TEST_STAT_LOG")" -eq 3 ]

echo "Permission helper tests passed"
