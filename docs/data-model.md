# Data model

The database stores metadata only. Source archives and images remain in the
read-only library.

## Core entities

- `User`: local account, password hash, legacy compatibility role, assigned
  role definition, source-access flag, active state, and timestamps.
- `Role` and `RolePermission`: system or custom role definitions and their
  stable permission keys.
- `UserLibrarySource`: explicit source grants for users without all-source
  access.
- `Session`: opaque server-side session with expiry and last use.
- `FavoriteList`: a private, named list owned by exactly one user.
- `FavoriteListItem`: a saved model or catalogue facet with a display snapshot;
  Creator entries reference a stable Creator Profile where available.
- `MetadataArtwork`: optimized custom artwork for a Creator Profile,
  Franchise, or Collection value.
- `CreatorProfile`: stable creator identity with canonical display name,
  description, artwork, active state, and optional merge target.
- `CreatorAlias`: globally unique normalized alternate spelling for a Creator
  Profile.
- `CreatorLink`: ordered, validated external link belonging to a Creator
  Profile; the legacy name key remains for 1.x compatibility.
- `CreatorMerge`: reversible merge snapshot for restoring source profiles and
  their model, alias, link, and favorite assignments.
- `LibrarySource`: display name, container root, parsing patterns, defaults,
  supported formats, and scan settings.
- `LibraryModel`: one indexed model, uniquely identified by source and relative
  path. The raw parsed Creator string remains and may resolve to a stable
  Creator Profile; Franchise, Series, and Collection remain text fields.
- `Archive`: the expected archive for a model, including format, size,
  modification time, scan state, and aggregate entry information.
- `ArchiveEntry`: cached file or directory metadata from an archive listing.
- `Image`: source image metadata, primary-image priority, and thumbnail state.
- `Tag`: custom label with optional colour and description.
- `ModelTag`: direct or inherited tag assignment.
- `FolderTagRule`: source-relative folder, tag, and recursive flag.
- `ScanRun`: status and statistics for one source scan.
- `ScanIssue`: structured warning or error produced by a scan.
- `AuditEvent`: an append-only snapshot of an accepted administrative action,
  with actor, action, safe target information, optional source association, and
  non-sensitive operational details.
- `TagAssignmentRule`, `TagAssignmentRuleTarget`, and
  `TagAssignmentRuleMatch`: canonical tag rules, their selected targets, and
  their evaluated matches.

Creator Profiles resolve canonical names and aliases during scans. Raw creator
strings remain for scan reproducibility and debugging; Creator Profile IDs are
the persistent relationship used by creator metadata, favorites, filters, and
navigation.

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
- Metadata artwork is unique per entity type and normalized catalogue value and
  is stored in SQLite so database backups remain self-contained.
- Saved models and tags use foreign keys plus a label snapshot. If the target is
  deleted, the entry remains visible as unavailable until its owner removes it.
- Saved Creator values use stable Creator Profile IDs, so profile-bound
  favorites survive renames and merges. Franchise, Series, and Collection use
  normalized keys while matching catalogue values still exist.
- FTS tables are derived indexes and can be rebuilt.
- `all_sources=true` grants a user access to current and future sources;
  explicit `UserLibrarySource` grants are then ignored.

## Change detection

Source files are compared using relative path, file size, and modification
time. Changed archive listings and thumbnails are regenerated. Manual metadata
and direct tags are retained across scans.
