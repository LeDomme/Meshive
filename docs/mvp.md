# Historical MVP scope (1.0)

This document records the completed 1.0 scope. For current capabilities and release changes, use the README and CHANGELOG.md.

- Single Docker image with FastAPI, built Vue assets, and 7-Zip CLI.
- SQLite database and separate thumbnail cache volumes.
- Traefik-compatible deployment and health check.
- Local admin and user accounts with no self-registration.
- Multiple dynamically configured read-only library sources.
- Testable directory and model-name patterns.
- Full and incremental scans.
- 7z, ZIP, and RAR listings without permanent extraction.
- JPEG, PNG, and WebP source images with generated WebP thumbnails.
- Authenticated gallery, search, filters, and model detail pages.
- Filters for creator, series/collection, source, status, and custom tags.
- Protected full-archive downloads.
- Direct and recursive folder tags.
- Scan history and actionable scan issues.

## Not included in 1.0

- Uploading, renaming, moving, or modifying source files.
- Public registration, OAuth, LDAP, and single sign-on.
- PostgreSQL, Meilisearch, and multi-instance deployment.
- Downloading individual files from inside archives.
- Integrated 3D previews.
- External metadata providers.
- Ratings, comments, and favourites.
- Per-source or per-model user permissions.

## Completion criteria

The MVP is complete when at least two differently structured sources can be
configured and scanned, all three archive formats can be listed and downloaded
after login, image changes refresh thumbnails, search and tags work, rescans
preserve manual metadata, and the source library requires no write access.
