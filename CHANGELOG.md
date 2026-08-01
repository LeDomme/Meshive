# Changelog

All notable changes to Meshive are documented in this file. Releases follow
[Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-08-01

### Changed

- Updated the FastAPI, Uvicorn, pydantic-settings, HTTPX, pytest, and
  pytest-cov dependency ranges.
- Updated the container build environments to Python 3.14 and Node.js 25.
- Updated the pinned major versions of the GitHub Actions used by CI.
- Grouped routine Dependabot updates while continuing to monitor all update
  levels.

### CI

- Added complete pull-request validation, including the container build and a
  runtime health smoke test without publishing the test image.

## [1.0.0] - 2026-08-01

### Added

- Read-only indexing of multiple dynamically configured model-library sources.
- Configurable directory and model-name patterns with optional series values.
- Incremental and scheduled scans with a visible, serialised scan queue.
- 7z, ZIP, and RAR archive inspection without permanent extraction.
- Authenticated gallery, FTS5 search, dependent filters, sorting, and model
  detail pages with image galleries and collapsible archive trees.
- Direct and inherited tags managed by administrators.
- Range-capable archive downloads and multi-archive bundle downloads.
- Local administrator and user management, mandatory initial passwords, and
  self-service account settings.
- Manual and scheduled SQLite backup archives, retention, validation, and
  guarded web-based restore with pre-restore safety backups.
- Token-protected first-run administrator setup and CLI bootstrap fallback.
- Standalone and Traefik Docker Compose examples with operating guides.

### Security

- Argon2id password hashing and revocable server-side sessions.
- Login rate limiting with `429` and `Retry-After` responses.
- Cross-site request protection, restrictive response headers, and CSP.
- Configurable archive, restore, scan, and download resource limits.
- Read-only source mounts and a hardened read-only runtime container.
- Locked and audited dependencies, immutable CI action references, SBOMs, and
  build provenance for published container images.

### Operations

- SQLite schema migrations run automatically at container startup.
- Health endpoint reports the running application version.
- Stable release tags publish semantic container tags and a GitHub Release.

[1.0.1]: ../../compare/v1.0.0...v1.0.1
[1.0.0]: ../../releases/tag/v1.0.0
