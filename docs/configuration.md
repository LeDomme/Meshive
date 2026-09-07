# Runtime configuration

Meshive reads variables prefixed with `MESHIVE_` at startup. The supplied
Compose files deliberately pass only deployment essentials. For an advanced
override, add the variable to the `environment:` section of the `meshive`
service; a value in Compose's `.env` file alone is used for interpolation and
is not automatically passed to the container.

All byte values below are raw bytes. Changing resource limits upward increases
the CPU, memory, disk, or archive-processing exposure of the installation.
There is no `MESHIVE_SECRET_KEY`: sessions use server-side, random opaque
tokens stored in the database, so there is no application signing secret to
generate or migrate.

## Runtime paths

| Variable | Default | Purpose and when to change it |
| --- | --- | --- |
| `MESHIVE_APP_NAME` | `Meshive` | Application name used in responses and UI metadata; normally never change. |
| `MESHIVE_ENVIRONMENT` | `development` | Use `production` behind HTTPS; it enables secure cookies. The standalone example intentionally remains development for direct trusted HTTP. |
| `MESHIVE_DATA_DIR` | `/app/data` | SQLite database and restore state. Change only with a matching writable mount. |
| `MESHIVE_CACHE_DIR` | `/app/cache` | Regenerable thumbnails and archive-image cache. Change only with a writable mount. |
| `MESHIVE_BACKUP_DIR` | `/backups` | Backup destination; use a separately protected writable mount. |
| `MESHIVE_FRONTEND_DIST` | `/app/frontend` | Built frontend files; normally never change. |
| `MESHIVE_ALLOWED_LIBRARY_ROOT` | `/models` | Read-only root beneath which library sources may be configured. Change only with a read-only source mount. |
| `MESHIVE_DATABASE_URL` | SQLite in `MESHIVE_DATA_DIR` | Advanced database-location override. One process only may access a SQLite database. |

## Identity and permissions

`PUID` and `PGID` are entrypoint variables, defaulting to `10001`; they must be
positive non-zero numeric IDs able to read the source mount. `MESHIVE_FIX_PERMISSIONS`
defaults to `auto`: it checks only the roots of the data, cache, and backup
mounts. `always` recursively repairs those writable mounts (potentially slow on
NFS); `never` performs no ownership changes for externally managed storage.
The source mount is never changed.

## Authentication and account recovery

| Variable | Default | Purpose |
| --- | --- | --- |
| `MESHIVE_SESSION_COOKIE_NAME` | `meshive_session` | Cookie name; change to avoid a collision on a shared host. |
| `MESHIVE_SESSION_LIFETIME_DAYS` | `7` | Server-side session lifetime (days). |
| `MESHIVE_AUTH_RATE_LIMIT_ATTEMPTS` | `5` | Failed logins permitted per window. |
| `MESHIVE_AUTH_RATE_LIMIT_WINDOW_SECONDS` | `60` | Login-rate-limit window (seconds). |
| `MESHIVE_SETUP_TOKEN` | unset | High-entropy token for the first administrator only; remove after setup. |
| `MESHIVE_PUBLIC_URL` | unset | Public `http(s)` base URL required for recovery email. |
| `MESHIVE_SMTP_HOST`, `MESHIVE_SMTP_USERNAME`, `MESHIVE_SMTP_PASSWORD`, `MESHIVE_SMTP_FROM` | unset | Required SMTP connection/account values for recovery email. Treat password as a secret. |
| `MESHIVE_SMTP_PORT` | `587` | SMTP port. |
| `MESHIVE_SMTP_SECURITY` | `starttls` | `ssl`, `starttls`, or `none`; production requires TLS. |
| `MESHIVE_SMTP_TIMEOUT_SECONDS` | `15` | SMTP connection timeout (seconds). |
| `MESHIVE_PASSWORD_RESET_LIFETIME_MINUTES` | `30` | Reset-token lifetime (minutes). |
| `MESHIVE_EMAIL_VERIFICATION_LIFETIME_HOURS` | `24` | Verification-token lifetime (hours). |

## Archive inspection and image extraction

| Variable | Default | Purpose |
| --- | --- | --- |
| `MESHIVE_ARCHIVE_COMMAND` | `7z` | Archive CLI executable. |
| `MESHIVE_ARCHIVE_TIMEOUT_SECONDS` | `120` | Archive-listing deadline (seconds). |
| `MESHIVE_ARCHIVE_MAX_ENTRIES` | `100000` | Maximum listed archive entries. |
| `MESHIVE_ARCHIVE_MAX_OUTPUT_BYTES` | `67108864` | Maximum archive-listing output bytes. |
| `MESHIVE_ARCHIVE_IMAGE_MAX_CANDIDATES` | `48` | Maximum selected archive images. |
| `MESHIVE_ARCHIVE_IMAGE_MAX_ENTRY_BYTES` | `67108864` | Maximum uncompressed bytes per image entry. |
| `MESHIVE_ARCHIVE_IMAGE_MAX_COMPRESSED_BYTES` | `67108864` | Maximum compressed bytes per image entry. |
| `MESHIVE_ARCHIVE_IMAGE_MAX_TOTAL_BYTES` | `268435456` | Maximum total selected image bytes. |
| `MESHIVE_ARCHIVE_IMAGE_MAX_PIXELS` | `100000000` | Maximum decoded pixels per image. |
| `MESHIVE_ARCHIVE_IMAGE_TIMEOUT_SECONDS` | `90` | Archive-image batch deadline (seconds). |
| `MESHIVE_ARCHIVE_IMAGE_THREADS` | `1` | 7-Zip extraction threads; increase only when CPU capacity permits. |

## Backup, concurrency, and gallery generation

| Variable | Default | Purpose |
| --- | --- | --- |
| `MESHIVE_BACKUP_MAX_RESTORE_BYTES` | `5368709120` | Largest accepted restore archive (bytes). |
| `MESHIVE_BACKUP_RESTORE_MIN_FREE_BYTES` | `67108864` | Required free-space reserve before restore (bytes). |
| `MESHIVE_MAX_CONCURRENT_SCANS` | `1` | Concurrent source scans. |
| `MESHIVE_MAX_CONCURRENT_DOWNLOADS` | `4` | Concurrent archive downloads. |
| `MESHIVE_THUMBNAIL_SIZE` | `480` | Thumbnail maximum edge (pixels). |
| `MESHIVE_THUMBNAIL_QUALITY` | `82` | WebP thumbnail quality. |
| `MESHIVE_THUMBNAIL_MAX_BYTES` | `65536` | Thumbnail output cap (bytes). |
| `MESHIVE_ARCHIVE_IMAGE_DETAIL_SIZE` | `1600` | Archive-image detail maximum edge (pixels). |
| `MESHIVE_ARCHIVE_IMAGE_DETAIL_MAX_BYTES` | `393216` | Archive-image detail output cap (bytes). |
| `MESHIVE_ARCHIVE_IMAGE_WEBP_METHOD` | `4` | WebP effort, 0 (fastest) through 6 (smallest/slowest). |

## Reverse proxy and public URL

The Traefik Compose example uses `MESHIVE_HOST`, `TRAEFIK_NETWORK`,
`TRAEFIK_ENTRYPOINTS`, and `TRAEFIK_CERT_RESOLVER` only for Compose labels and
network interpolation. They are not Meshive runtime settings. Set
`MESHIVE_PUBLIC_URL` as well when password recovery email is enabled.
