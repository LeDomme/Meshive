#!/bin/sh

validate_runtime_identity() {
    case "$PUID" in
        '' | *[!0-9]*)
            echo "PUID and PGID must be positive numeric IDs." >&2
            return 1
            ;;
    esac
    case "$PGID" in
        '' | *[!0-9]*)
            echo "PUID and PGID must be positive numeric IDs." >&2
            return 1
            ;;
    esac
    if [ "$PUID" -eq 0 ] || [ "$PGID" -eq 0 ]; then
        echo "PUID and PGID must not be 0." >&2
        return 1
    fi
}

ensure_dir_owner() {
    dir="$1"
    mkdir -p "$dir"
    echo "Checking ownership of $dir"
    if ! current_owner="$(stat -c '%u:%g' "$dir")"; then
        echo "Could not read ownership of $dir." >&2
        return 1
    fi
    if [ "$current_owner" = "$PUID:$PGID" ]; then
        echo "Ownership already correct for $dir"
        return 0
    fi
    echo "Setting ownership of $dir to $PUID:$PGID"
    if ! chown "$PUID:$PGID" "$dir"; then
        echo "Could not set ownership of $dir. Set MESHIVE_FIX_PERMISSIONS=never when permissions are managed outside the container." >&2
        return 1
    fi
}

prepare_runtime_dirs() {
    mode="${MESHIVE_FIX_PERMISSIONS:-auto}"
    case "$mode" in
        auto)
            for dir in "$@"; do
                ensure_dir_owner "$dir" || return 1
            done
            ;;
        always)
            for dir in "$@"; do
                mkdir -p "$dir"
                echo "Recursively fixing ownership of $dir"
                if ! chown -R "$PUID:$PGID" "$dir"; then
                    echo "Could not recursively set ownership of $dir." >&2
                    return 1
                fi
            done
            ;;
        never)
            for dir in "$@"; do
                mkdir -p "$dir"
                echo "Skipping ownership changes for $dir"
            done
            ;;
        *)
            echo "MESHIVE_FIX_PERMISSIONS must be auto, always, or never." >&2
            return 1
            ;;
    esac
}
