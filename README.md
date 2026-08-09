<p align="center">
  <img src="resources/meshhive_with_name.webp" alt="Meshive" width="460">
</p>

# Meshive

Meshive is a self-hosted catalogue for archived 3D-print models.

It indexes one or more read-only model libraries, generates thumbnails in a
separate cache, lists the contents of 7z, ZIP, and RAR archives, and provides
authenticated downloads without modifying the source library.

Full archive downloads require an authenticated Meshive session and support
HTTP range requests for large files and resumable transfers.

## Project status

Meshive 1.3.0 is the current stable release series. The application is intended
for a single self-hosted instance and is designed for multi-terabyte,
read-only model libraries. Architecture and operating procedures live in the
[`docs`](docs/) directory.

## Stack

- FastAPI and SQLAlchemy
- SQLite with FTS5
- Vue 3 and TypeScript
- 7-Zip CLI for archive inspection
- One runtime container behind Traefik

## Development

Meshive can be run in development after installing the backend and frontend
dependencies:

```bash
cd backend
python -m venv .venv
pip install -e ".[dev]"
uvicorn meshive.main:app --reload
```

```bash
cd frontend
npm ci --include=dev
npm run dev
```

The frontend development server proxies `/api` to FastAPI on port `8000`.

## Filesystem identity

Set `PUID` and `PGID` to the numeric user and group that may read the mounted
model library. The image has an unprivileged internal default, but deployments
must derive both values from the permissions of their own storage rather than
copying example IDs.

Only Meshive's database and thumbnail cache are adjusted to this identity. The
read-only model library is never changed.

## Docker Compose

Copy `.env.example` to `.env`, adjust the runtime identity and external volume
names, then pull and start the published image:

```bash
docker compose pull
docker compose up -d
```

[`compose.yaml`](compose.yaml) publishes Meshive directly on the configured host
port. [`compose.traefik.yaml`](compose.traefik.yaml) is a complete alternative
for an existing Traefik network and does not publish a host port. Deployment,
volume, and reverse-proxy details are covered by the
[`production deployment guide`](docs/production-deployment.md).

The direct HTTP example is intended for a trusted network or evaluation. Use
HTTPS and production mode whenever Meshive is exposed beyond that boundary.

To build the image locally instead, run `docker build -t meshive:local .` and
set `MESHIVE_IMAGE=meshive:local` in `.env` before starting Compose.

Stable deployments should use a concrete semantic tag such as `1.3.0` or an
immutable digest. `latest` is updated only by a stable version tag. The `edge`
tag follows successful builds from `main` and is intended for testing upcoming
changes rather than production deployments.

Library source patterns, including optional series and multiple model-name
alternatives, are documented in
[`docs/source-patterns.md`](docs/source-patterns.md).

Database backup and container-based restore procedures are documented in
[`docs/backup-and-restore.md`](docs/backup-and-restore.md).

Per-source scan scheduling is documented in
[`docs/automatic-scans.md`](docs/automatic-scans.md).

Private per-user favorite lists are documented in
[`docs/favorite-lists.md`](docs/favorite-lists.md).

Case-insensitive automatic tags derived from archive entry names and paths are
documented in [`docs/automatic-tagging.md`](docs/automatic-tagging.md).

Meshive can select safe, bounded JPEG, PNG, and WebP gallery images from 7z,
ZIP, and RAR archives without altering or permanently extracting the source
archive. Selection rules, cache behaviour, and resource limits are documented
in [`docs/archive-images.md`](docs/archive-images.md).

Catalogue filters can be reordered and saved per user. Administrators can also
filter incomplete models; that status is not exposed to regular users. Opening
a model from the catalogue preserves the active filters and sort order, which
are used by the previous/next model navigation on its detail page.

Scan and download concurrency settings are documented in
[`docs/resource-limits.md`](docs/resource-limits.md).

## Dependency security

Frontend dependencies are locked in `frontend/package-lock.json`; local and
container builds install the required build dependencies with
`npm ci --include=dev`. GitHub Actions builds the frontend and rejects
high-severity npm advisories before publishing an image. Runtime Python
dependencies are checked with `pip-audit`.

Dependabot checks npm, Python, Docker, and GitHub Actions dependencies monthly.
Workflow actions are pinned to immutable commit SHAs, with their release tags
retained as comments so automated updates can maintain them.

To deploy the Traefik example, select its Compose file explicitly:

```bash
docker compose -f compose.traefik.yaml pull
docker compose -f compose.traefik.yaml up -d
```

## Create the first administrator

On a fresh installation, configure a long random `MESHIVE_SETUP_TOKEN` and open
Meshive in a browser. The first-run page creates and signs in the initial
administrator. It is permanently disabled as soon as the first user exists.

Failed logins are limited to five attempts per normalized username within 60
seconds; initial setup failures use a separate global limit. The defaults can
be changed with
`MESHIVE_AUTH_RATE_LIMIT_ATTEMPTS` and
`MESHIVE_AUTH_RATE_LIMIT_WINDOW_SECONDS`.

Alternatively, after the container has started and applied its migrations, open
a container console and run:

```bash
meshive create-admin --username admin
```

The command securely prompts for a password and does not expose it as a command
argument. When the container console runs as root, use:

```bash
gosu "$PUID:$PGID" meshive create-admin --username admin
```

With the standalone Compose file, the equivalent host command is:

```bash
docker compose exec meshive \
  sh -lc 'gosu "$PUID:$PGID" meshive create-admin --username admin'
```

Optional verified-email password recovery and the container-side emergency
reset command are documented in [Password recovery](docs/password-recovery.md).

## License

Meshive is licensed under the [GNU Affero General Public License version 3
only](LICENSE), identified by the SPDX expression `AGPL-3.0-only`. The license
does not include the option to use a later version of the GNU Affero General
Public License. See [NOTICE](NOTICE) for the explicit project licensing notice.

Release changes are recorded in [`CHANGELOG.md`](CHANGELOG.md). Please report
security vulnerabilities according to [`SECURITY.md`](SECURITY.md).
