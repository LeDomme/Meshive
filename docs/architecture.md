# Architecture

## Overview

Meshive is a modular monolith distributed as one runtime container.

```text
Browser -> [reverse proxy] -> FastAPI
                                |-- bundled Vue application
                                |-- SQLite metadata database
                                |-- 7-Zip CLI
                                `-- read-only library sources
```

The archive library is never modified by Meshive. SQLite data and generated
thumbnails use separate writable volumes.

The runtime process uses configurable numeric `PUID` and `PGID` values so NFS
and NAS permissions can be matched without granting the application root
access. The root entrypoint only prepares the writable data/cache volumes and
then drops privileges before migrations and the web server start.

Normal startup checks only writable volume roots before dropping privileges; an
explicit repair mode can recursively fix legacy volume ownership when required.

## Components

### Backend

FastAPI provides authentication, administration, catalogue APIs, protected
images and downloads, scan orchestration, and the bundled frontend.

SQLAlchemy and Alembic isolate persistence details and keep a future move from
SQLite to PostgreSQL possible.

SQLite FTS5 indexes model names, creators, franchises, series, collections, and
custom tags. Database triggers keep the derived index synchronized with model
and tag changes.

### Frontend

The user interface is a Vue 3 TypeScript application. English is the initial
language. User-facing strings should remain centralised so localisation can be
added later.

### Search

SQLite FTS5 indexes model, creator, and series/collection names. Archive entry
names are searchable on a model detail page but are not part of global search
in the MVP.

### Archive inspection

An archive reader abstraction invokes the container's `7z` CLI with fixed
arguments and no shell. The Debian RAR codec is installed separately.
The MVP supports 7z, ZIP, and RAR. Listings are cached and refreshed when the
archive size or modification time changes. Archives are never permanently
extracted.

### Library sources

Administrators configure multiple sources that already exist inside the
container, normally below `/models`. Container mounts are configured outside
Meshive and must be read-only.

Each source has a directory pattern and optional model-name pattern. For
example:

```text
Directory: {creator_folder}/{franchise}/{model_folder}
Model name: {franchise} - {model} - by {creator}
```

or:

```text
Directory: {franchise}/{model_folder}
Model name: {franchise} - {model} - by {creator}
```

The UI provides a safe test and preview facility. Patterns are compiled
internally; arbitrary executable expressions are not accepted.

### Images and thumbnails

Original JPEG, PNG, and WebP images remain read-only. Meshive detects changes
using relative path, size, and modification time and regenerates derived WebP
thumbnails in its cache. Embedded archive-image candidates are selected with
bounded, deterministic rules and are never extracted into a library source.
Valid archive images take presentation priority while images beside archives
remain available as a fallback. Manual primary-image choices survive rescans
while the selected image exists.

Generated thumbnails are addressed by a source signature rather than their
original filename and are delivered through authenticated API routes.

## Security boundaries

- Every library mount is read-only.
- Database paths are relative to a configured and approved source root.
- Resolved paths must remain inside that root, including symlink resolution.
- User input is never interpolated into archive commands.
- Models, images, listings, and downloads require authentication.
- There is no public registration.
- Passwords use Argon2id and sessions are server-side.
- Archive processes have concurrency, runtime, and output limits.
- State-changing browser API requests with a foreign origin are rejected.
- The runtime root filesystem is read-only; only explicit data volumes and a
  size-limited temporary filesystem are writable.
