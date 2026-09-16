# Meshive Agent Instructions

Meshive is a self-hosted web application for managing a large collection of archived 3D models.

## Project context

Current production-scale library:

* 4,000+ models
* approximately 3.42 TB and growing
* multiple dynamically configurable library sources
* source libraries are mounted read-only
* archives must never be permanently extracted
* archive formats include 7z, ZIP and RAR
* model folders normally contain one compressed archive and one or more images

Meshive is an established application. Do not treat the repository as a new/MVP project or redesign existing architecture unless explicitly requested.

## Stack

* Backend: FastAPI
* Database: SQLite with FTS5
* ORM / migrations: SQLAlchemy / Alembic
* Frontend: Vue 3 + TypeScript
* Deployment: single Meshive runtime container, typically behind Traefik
* Initial UI language: English

Use the existing architecture, patterns and conventions in the repository.

Relevant architecture and technical documentation is located in `docs/`.

## Core constraints

* Never modify files or directories in mounted model libraries.
* Library sources must remain read-only.
* Never permanently extract archives.
* Preserve compatibility with existing databases and installations unless a task explicitly requires a breaking change.
* Preserve source scoping and permission boundaries.
* Do not leak information from library sources a user cannot access.
* Prefer stable identifiers over mutable display strings for persistent relationships.
* Avoid loading entire large libraries or archives into memory when pagination, SQL queries or lazy loading can be used.
* Avoid N+1 database queries.
* Changes must remain practical for libraries containing thousands of models and hundreds of thousands of cached/archive entries.

## Development workflow

Before implementing a task:

1. inspect the relevant existing code and tests
2. read only the documentation necessary for the task
3. reuse existing patterns instead of creating parallel architectures
4. determine the smallest coherent change that satisfies the requested scope

Do not perform broad repository-wide analysis unless the task requires it.

When continuing an existing task or interrupted session:

* inspect the current branch, worktree and uncommitted changes first
* preserve valid existing work
* do not restart the implementation from scratch
* continue only the remaining work

## Scope discipline

Implement only the requested task.

Do not opportunistically:

* refactor unrelated code
* redesign established APIs
* migrate unrelated data
* introduce future-roadmap features
* clean up unrelated lint or test failures

If a larger change is clearly required, report it rather than silently expanding the scope.

## Compatibility

For additive changes, preserve existing APIs and behavior unless explicitly instructed otherwise.

When replacing legacy mechanisms:

* prefer an additive migration path
* keep required compatibility fallbacks during the supported 1.x series
* do not silently discard or rewrite user metadata
* migration conflicts must fail clearly rather than guess

Database migrations must be deterministic and tested against realistic historical schemas where relevant.

Historical migration fixtures must continue to represent their historical schema and must not accidentally use current ORM definitions.

## Testing

During development:

* run focused tests for changed functionality first
* run relevant regression tests for affected subsystems
* run broader suites when the change has broad impact or before completing a PR
* run lint/type checks relevant to changed files
* run `git diff --check`

Do not disable tests, skip tests, weaken assertions or remove CI checks merely to make CI pass.

If multiple failures appear, look for a common root cause instead of patching individual symptoms.

## Pull requests and CI

Unless explicitly instructed otherwise, Codex may:

* create/switch branches
* commit changes
* push branches
* create or update pull requests

After creating or updating a PR:

* monitor the required CI checks
* investigate failed checks from their actual logs
* reproduce failures locally when practical
* fix PR-caused failures within scope
* push the fix and check CI again

Continue until required CI checks are green or a genuine blocker requires user input.

Do not repeatedly report intermediate status when autonomous progress is possible.

## Git restrictions

Never without explicit user instruction:

* merge a pull request
* create a release
* create or push a version tag

Do not commit local planning/roadmap files that are intentionally untracked.

In particular, files such as local `CODEX_DEVELOPMENT_*.md` planning documents are working instructions unless explicitly requested for version control.

## Communication

* Communicate with the user in German.
* Code, identifiers, comments, commit messages, pull-request titles/descriptions and repository documentation should be in English unless the existing file requires otherwise.
* Keep progress and final reports concise.
* Ask for user input only for genuine blockers or decisions that cannot be derived safely from existing architecture or task requirements.

A successful implementation report should normally contain only:

* PR link
* relevant commit(s)
* short summary of implemented behavior
* tests / CI result
* important intentionally deferred items

## Product capabilities

Existing Meshive capabilities include, among others:

* catalogue/gallery and model detail views
* model, creator, franchise/collection and metadata search/filtering
* lazy archive browsing without permanent extraction
* archive downloads
* multiple library sources with configurable path/name parsing
* manual and recursive custom tags
* local authentication without public registration
* role/permission and source-scoped access control
* favorites
* metadata artwork and creator links
* backup/restore
* scan, smart/incremental scan and targeted rescan workflows
* audit functionality

Consult the current code and `docs/` for authoritative details rather than assuming this list is exhaustive.
