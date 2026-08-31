# Historical implementation plan (1.0)

All milestones below are complete and retained as implementation history. For current release work, use CHANGELOG.md and the release checklist.
## Milestone 1: Foundation

- Architecture and scope documentation.
- FastAPI and Vue scaffolds.
- Multi-stage runtime image and Compose examples.
- Health endpoint and frontend/backend connectivity check.

## Milestone 2: Persistence and source configuration

- [x] SQLAlchemy engine and initial Alembic migration.
- [x] Initial `LibrarySource` entity and constraints.
- [x] Library-source CRUD API, closed until admin authentication is available.
- [x] Safe path-pattern parser with preview endpoint.
- [x] Unit tests for the two confirmed source layouts.
- [x] Source-management frontend.

## Milestone 3: Authentication

- [x] Argon2id password hashing.
- [x] Server-side sessions and secure cookies.
- [x] Admin bootstrap command.
- [x] User administration API and route protection.
- [x] Login and logout interface.
- [x] Token-protected first-run administrator setup.
- [x] User administration frontend.

## Milestone 4: Scanner

- [x] Full and incremental source scans.
- [x] 7z, ZIP, and RAR listing adapter.
- [x] Image discovery and deterministic primary selection.
- [x] WebP thumbnail cache generation and protected delivery.
- [x] Scan runs, issues, change detection, and missing-item handling.
- [x] Per-source hourly, daily, and weekly automatic scan schedules.

## Milestone 5: Catalogue

- [x] Gallery, pagination, basic search, and metadata filters.
- [x] Replace basic search with the planned FTS5 index.
- [x] Model details, image gallery, and archive-content browser.
- [x] Direct and inherited custom tags.
- [x] Protected range-capable archive downloads.

## Milestone 6: Production hardening

- [x] Resource and concurrency limits.
- [x] Backup and recovery workflow.
- [x] Traefik deployment test.
- [x] Integration tests against representative sample libraries.
- [x] Security review and release documentation.
