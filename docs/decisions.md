# Technical decisions

## Accepted defaults

- English is the initial UI language.
- Runtime paths use normalised POSIX separators.
- Source roots must be within administrator-approved container roots.
- Series/collection records have `franchise`, `collection`, or `unspecified`
  kinds.
- Parsed metadata can have persistent manual display overrides.
- Scans can be started manually or scheduled per source. Concurrent requests
  enter a visible serialised queue.
- Thumbnail outputs are WebP and never upscale the original.
- A manual primary image wins over deterministic filename-based selection.
- Zero archives mark a model as incomplete. Multiple archives are indexed
  independently and belong to the same model.
- Password-protected archives are not given stored passwords.
- FastAPI initially serves protected downloads with range support verified by
  integration tests.
- SQLite data and cache storage must not reside on network mounts.
- Runtime filesystem access uses configurable numeric `PUID` and `PGID`;
  `/models` remains read-only and is never ownership-adjusted.
- Vue 3, TypeScript, Vue Router, Pinia, and a small CSS layer form the frontend.

## Verified production constraints

- The production topology uses one Meshive runtime container. Public exposure
  requires an HTTPS reverse proxy; Traefik is supplied as one example.
- SQLite data stays on a local Docker volume; model and backup mounts may use
  network storage.
- Source libraries, including symlink targets, must remain inside the approved
  `/models` root and are mounted read-only.
- Session lifetime, schedules, archive limits, concurrency, and restore limits
  are configurable through the environment and have bounded defaults.
