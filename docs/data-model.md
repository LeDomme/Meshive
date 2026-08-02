# Data model

The database stores metadata only. Source archives and images remain in the
read-only library.

## Core entities

- `User`: local account, password hash, role, active state, and timestamps.
- `Session`: opaque server-side session with expiry and last use.
- `FavoriteList`: a private, named list owned by exactly one user.
- `FavoriteListItem`: a saved model or catalogue facet with a display snapshot.
- `LibrarySource`: display name, container root, parsing patterns, defaults,
  supported formats, and scan settings.
- `Creator`: parsed creator identity plus optional manual display override.
- `Group`: a franchise, collection, or unspecified grouping.
- `LibraryModel`: one indexed model, uniquely identified by source and relative
  path.
- `Archive`: the expected archive for a model, including format, size,
  modification time, scan state, and aggregate entry information.
- `ArchiveEntry`: cached file or directory metadata from an archive listing.
- `Image`: source image metadata, primary-image priority, and thumbnail state.
- `Tag`: custom label with optional colour and description.
- `ModelTag`: direct or inherited tag assignment.
- `FolderTagRule`: source-relative folder, tag, and recursive flag.
- `ScanRun`: status and statistics for one source scan.
- `ScanIssue`: structured warning or error produced by a scan.

The first scanner migration stores parsed creator, franchise, and collection
values directly on `LibraryModel`. Normalized browse/filter tables can be
derived from these values later without rereading source archives.

## Important constraints

- A model key is `(library_source_id, relative_path)`.
- Paths stored for library content are relative, normalised POSIX paths.
- A model may contain one or more archives. Each archive keeps its own cached
  content listing and change-detection metadata.
- Supported archive formats are `7z`, `zip`, and `rar`.
- Models are marked missing rather than immediately deleted.
- Parsed metadata and manual overrides are stored separately.
- Manual and inherited tags are distinct so folder rules can be removed safely.
- Favorite-list names are unique per user after Unicode-aware normalization.
- Favorite-list ownership is enforced on every list and item operation.
- Saved models and tags use foreign keys plus a label snapshot. If the target is
  deleted, the entry remains visible as unavailable until its owner removes it.
- Saved Creator, Franchise, Series, and Collection values use normalized keys.
  They link to the matching catalogue filter while that value still exists.
- FTS tables are derived indexes and can be rebuilt.

## Change detection

Source files are compared using relative path, file size, and modification
time. Changed archive listings and thumbnails are regenerated. Manual metadata
and direct tags are retained across scans.
