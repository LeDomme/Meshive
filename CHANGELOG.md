# Changelog

All notable changes to Meshive are documented in this file. Releases follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.5.0] - 2026-09-01
### Added
- Single-pass source discovery, explicit live scan phases, and Smart Scan for unchanged healthy models.
- Lightweight, admin-only diagnostics without recursive storage traversal.
- Playwright frontend regression-test foundation and E2E documentation.
### Changed
- Reduced redundant scan-progress writes and fixed pending scan cancellation timestamps.

## [1.4.1] - 2026-08-31
### Fixed
- Scheduled scan evaluation failures are now logged without stopping the scheduler.
- Invalid persisted scan timezones now produce one actionable warning per source and timezone.
- Corrected the documented default archive-image pixel limit to 100 megapixels.

## [1.4.0] - 2026-08-31
### Added
- Added administrator scan controls, live activity, statistics, and per-model scan issue history.
- Added batch model selection with queued rescan and picture-reset actions.
- Added archive-image reconciliation, gallery carousel navigation, and support for MPO archive images.
### Changed
- Archive-image selection is deterministic, bounded, and reports one aggregated administrator warning when valid candidates are skipped by configured safety limits.
- Container startup now checks mounted directory roots by default; recursive permission repair is an explicit one-time operation suitable for NFS-backed caches.
- Expanded scan-mode and archive-image cache reconciliation coverage for incremental, targeted, and full scans.
## [1.3.0] - 2026-08-10

### Added

- Added bounded extraction of selected JPEG, PNG, and WebP gallery images from
  7z, ZIP, and RAR archives. Derived WebP variants are stored only in the
  Meshive-managed cache; source libraries remain read-only.
- Added per-user drag-and-drop catalogue-filter ordering.
- Added previous and next navigation between model details while preserving the
  active catalogue search, filters, and sort order.

### Changed

- Catalogue controls now have refined keyboard and responsive behaviour,
  animated reordering, and non-wrapping filter labels.
- Removed unused source-default metadata. The incomplete-model status filter
  is now available to administrators only.
- Reduced the default maximum thumbnail size to 64 KiB and full archive-image
  gallery variant size to 384 KiB.

### Security

- Archive-image processing validates actual image content and applies bounded
  candidate, extraction, pixel, processing-time, and cache-output limits.

## [1.2.0] - 2026-08-02

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
- Tag descriptions are shown in a compact tooltip when a tag is hovered or
  focused with the keyboard.
- Unsaved model favorite buttons now provide a highlighted add state on hover
  and keyboard focus.

### Upgrade notes

- Startup automatically applies the model-variant, favorite-list, metadata
  artwork, and automatic-tagging migrations.
- Favorite lists are stored in Meshive's SQLite database and are included in
  regular database backups together with custom metadata artwork.
- Before upgrading, create and validate a backup. Meshive 1.1.0 must not be run
  against a migrated 1.2 database; restore the pre-upgrade backup before
  rolling back to the previous image.

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

[Unreleased]: ../../compare/v1.4.0...HEAD
[1.4.0]: ../../compare/v1.3.0...v1.4.0
[1.3.0]: ../../compare/v1.2.0...v1.3.0
[1.2.0]: ../../compare/v1.1.0...v1.2.0
[1.1.0]: ../../compare/v1.0.1...v1.1.0
[1.0.1]: ../../compare/v1.0.0...v1.0.1
[1.0.0]: ../../releases/tag/v1.0.0
