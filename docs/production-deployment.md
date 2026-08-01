# Production deployment

Meshive 1.0 is distributed as one container image. It expects a local writable
SQLite data volume, a disposable thumbnail cache, a separate backup target,
and one or more read-only model-library mounts. The supported runtime topology
uses exactly one Meshive application process. It can publish a host port
directly or run behind an HTTPS reverse proxy such as Traefik.

## Before deployment

- Create or identify the external Docker volume containing the models.
- Determine the numeric `PUID` and `PGID` that can read that volume.
- Create persistent locations for `/app/data` and `/app/cache`, plus an
  independently protected external Docker volume for `/backups`.
- Keep `/app/data` on local storage, not NFS. The model and backup mounts may be
  network storage.
- Authenticate Docker with GHCR when the container image is private.
- Generate a long random first-run setup token.

The model mount must be read-only. Meshive never uploads, renames, deletes, or
extracts source-library files.

## Container contract

The image can be deployed by any OCI-compatible container manager. It exposes
HTTP on port `8000`, includes its own health check, and expects these mounts:

| Container path | Access | Purpose |
| --- | --- | --- |
| `/app/data` | read/write | Local persistent SQLite data and restore state |
| `/app/cache` | read/write | Regenerable thumbnail cache |
| `/backups` | read/write | Independently protected backup destination |
| `/models` | read-only | One library tree or multiple mounted subdirectories |
| `/tmp` | read/write tmpfs | Bounded temporary runtime files |

The entrypoint starts with the minimal capabilities needed to prepare writable
volume ownership, then runs migrations and Meshive as `PUID:PGID`. Configure
those variables instead of overriding the container `user`. Only one Meshive
container may use a given SQLite data volume at a time. Supported environment
variables and limits are listed in [`.env.example`](../.env.example).

## Docker Compose

Meshive includes two self-contained examples:

- [`compose.yaml`](../compose.yaml) publishes the configured HTTP port directly
  on the host and has no reverse-proxy dependency. It defaults to development
  mode so authentication cookies work over direct HTTP and must not be exposed
  to an untrusted network.
- [`compose.traefik.yaml`](../compose.traefik.yaml) connects only to an existing
  Traefik network, enables production mode, and configures HTTPS routing
  through labels.

Copy [`.env.example`](../.env.example) to `.env`. Derive deployment values from
the target host instead of copying values from another installation:

| Variable | Deployment-specific value |
| --- | --- |
| `MESHIVE_IMAGE` | Published image tag or immutable digest |
| `MESHIVE_MODELS_VOLUME` | Existing external volume containing the libraries |
| `MESHIVE_BACKUP_VOLUME` | Existing external volume for independent backups |
| `MESHIVE_SETUP_TOKEN` | Newly generated, high-entropy one-time secret |
| `PUID` / `PGID` | Numeric identity permitted to read the model storage |
| `MESHIVE_ENVIRONMENT` | `development` for direct HTTP; `production` behind HTTPS |
| `MESHIVE_PORT` | Host port for the standalone example |
| `MESHIVE_HOST` | Public DNS name for the Traefik example |
| `MESHIVE_PUBLIC_URL` | Public base URL used in optional recovery emails |
| `MESHIVE_SMTP_*` | Optional SMTP account and TLS mode for password recovery |
| `TRAEFIK_NETWORK` | Existing reverse-proxy container network |
| `TRAEFIK_ENTRYPOINTS` | HTTPS entrypoint configured on the proxy |
| `TRAEFIK_CERT_RESOLVER` | Certificate resolver configured on the proxy |

If the image is private, authenticate the container runtime with the selected
registry using a read-only package token. Do not store registry credentials in
the Compose file or commit them to the repository.

The following commands use the standalone example. When using Traefik, add
`-f compose.traefik.yaml` after `docker compose` instead:

```sh
docker compose pull
docker compose up -d
docker compose ps
```

The supplied Compose deployment creates named data and cache volumes. The model
and backup volumes are external so removing the application deployment cannot
remove those files. Create `MESHIVE_BACKUP_VOLUME` before deployment and back
it up independently; it may point to NFS-backed storage. The configured model
volume must already exist.

Container-management interfaces can import either Compose file. Meshive has no
dependency on a particular management interface.

## First run

1. Start the Compose deployment and wait for the health check to become healthy.
2. Open the configured host port, or the HTTPS host when using Traefik.
3. Enter the setup token, administrator username, and a strong password.
4. Remove `MESHIVE_SETUP_TOKEN` from `.env` after the administrator exists and
   recreate the container.
5. Configure library sources below `/models` and test their patterns.
6. Run the first source scan.
7. Configure and test automatic backups before relying on the catalogue.

The setup endpoint permanently refuses another initial administrator once any
user exists. An administrator can also be created from the host:

```sh
docker compose exec meshive \
  sh -lc 'gosu "$PUID:$PGID" meshive create-admin --username admin'
```

## Verification

The unauthenticated `/api/health` endpoint on the configured HTTP or HTTPS
address reports the running release.

Expected response for this release:

```json
{"status":"ok","version":"1.0.1"}
```

Also verify login, source scanning, thumbnails, archive trees, individual and
bundle downloads, manual backup, scheduled backup, and one controlled restore.

## Upgrade

1. Create a manual backup and confirm that it is listed as completed.
2. Record the currently deployed image tag or digest.
3. Read `CHANGELOG.md` for migration or configuration notes.
4. Change `MESHIVE_IMAGE` to the new release tag and run:

   ```sh
   docker compose pull
   docker compose up -d
   ```

5. Meshive applies database migrations automatically before starting.
6. Check `/api/health`, container logs, login, catalogue, and backups.

Do not run two Meshive containers against the same SQLite data volume.

## Rollback

Application rollback and database rollback are separate operations. If the new
release applied a database migration, stop it and restore the pre-upgrade
backup using the documented restore procedure before deploying the old image.
Never start an older release against a database whose schema it does not
support.

See [`backup-and-restore.md`](backup-and-restore.md) for web and container-based
recovery procedures and [`.env.example`](../.env.example) for all supported
runtime limits.

The tag workflow also creates the GitHub Release. Repository Actions settings
must permit the workflow `GITHUB_TOKEN` to write repository contents.
