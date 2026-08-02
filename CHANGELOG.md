# Changelog

All notable changes to Meshive are documented in this file. Releases follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Added optional model variants with case-insensitive Variant, Version,
  Edition, Revision, Rev, and Ver identifiers in source name patterns.
- Added private per-user favorite lists for models, creators, franchises,
  series, collections, and tags, including catalogue links and unavailable-item
  handling.
- Added direct catalogue-category assignment from favorite lists, positive
  saved states with one-click removal, and multi-list management in the save
  dialog.
- Added Meshive-themed fallback artwork and administrator-managed custom WebP
  artwork for creators, franchises, and collections.
- Added administrator-managed automatic tag rules with case-insensitive
  archive-entry matching, independently tracked provenance, immediate
  re-evaluation, and scan-result statistics.

### Changed

- Renamed the Creator administration section to Metadata and combined creator
  links with catalogue artwork management.
- Existing tags can now be renamed and have their colour or description
  corrected without losing model assignments, folder rules, automatic rules,
  or favorite-list references.

### Upgrade notes

- Startup automatically applies the model-variant, favorite-list, metadata
  artwork, and automatic-tagging migrations.
- Favorite lists are stored in Meshive's SQLite database and are included in
  regular database backups together with custom metadata artwork.

## [1.1.0] - 2026-08-02

### Added

- Added exact model-name filtering, searchable filter menus, dependent facet
  values, on-demand full-text search, and expanded catalogue pagination.
- Added filter-aware links for model metadata and tags on detail pages while
  preserving catalogue state when navigating back.
- Added administrator-managed creator metadata with multiple typed links for
  websites, memberships, marketplaces, and custom destinations.
- Added a privacy-conscious active-session overview with individual revocation
  and an option to sign out all other sessions.
- Added optional verified email addresses and secure, rate-limited password
  recovery through configurable SMTP delivery.
- Added email-verification controls for users and administrators plus a secure
  container-side emergency password-reset command.

### Changed

- Stable container tags remain release-only, while successful builds from
  `main` publish the `edge` development tag.
- Improved responsive administration layouts and catalogue filter controls.
- Updated the pinned `pip-audit` development dependency to 2.10.1.

### Security

- Password-reset and email-verification tokens are single-use, expire, and are
  invalidated with affected sessions after sensitive account changes.
- Recovery requests return neutral responses and are rate limited to avoid
  account discovery and mail abuse.
- Database restores invalidate all sessions and outstanding action tokens.

### Upgrade notes

- Startup automatically applies the creator-link, session-metadata, and account
  recovery migrations.
- Before upgrading, create and validate a backup. Meshive 1.0.1 must not be run
  against the migrated 1.1 schema; restore the pre-upgrade database before
  rolling back to the previous image.

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

[1.1.0]: ../../compare/v1.0.1...v1.1.0
[1.0.1]: ../../compare/v1.0.0...v1.0.1
[1.0.0]: ../../releases/tag/v1.0.0
