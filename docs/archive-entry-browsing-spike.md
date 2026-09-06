# Design spike: lazy, paginated archive entries

**Status:** proposed for Meshive 1.6.1 P4. This is a design gate only: it
changes no runtime API, schema, scanner, or frontend code.

## Decision

Implement P4 after this gate, using a separate, derived browse-node index. Do
not paginate the current flat `ArchiveEntry` response and do not remove the
tree. A browse node exists for every physical entry and for every implied parent
directory. `ArchiveEntry` remains the authoritative record of what the archive
listing contained.

This preserves trees such as `STL/parts/body.stl` even when 7-Zip emitted no
explicit `STL` or `STL/parts` directory entries. It also prevents synthetic
directories from changing `Archive.entry_count`, automatic-tag evidence, or
image selection.

## Current behaviour and measured baseline

`GET /api/models/{model_id}` currently loads every `ArchiveEntry` ORM object for
each archive when the user has `archives.view_entries`:

```python
select(ArchiveEntry)
    .where(ArchiveEntry.archive_id == archive.id)
    .order_by(ArchiveEntry.path.collate("NOCASE"))
```

It then iterates those objects for archive statistics and serializes all of them
as `ArchiveRead.entries`. `ModelDetailView` constructs an in-browser tree from
the complete array. Thus database rows, Python ORM objects, JSON response, and
browser tree all scale with every entry in every archive of the detail page.

The following reproducible in-process SQLite/TestClient measurement created one
visible model, one ready ZIP archive, and entries named
`folder-NNN/file-NNNNNN.stl`. It measured `len(response.content)`, wall-clock
request time, and `tracemalloc` peak around the request. Values are a local
baseline, not a performance SLO.

| physical ArchiveEntry rows | JSON payload | request time | process peak |
| ---: | ---: | ---: | ---: |
| 1,000 | 156,331 bytes | 0.107 s | 5.4 MiB |
| 10,000 | 1,577,335 bytes | 0.561 s | 26.8 MiB |
| 100,000 | 15,967,339 bytes | 5.571 s | 277.1 MiB |

Reproduce with the backend virtual environment and an empty temporary data
directory. The fixture is deliberately synthetic and uses the same FastAPI test
client and `catalog_client()` setup as `backend/tests/test_catalog_api.py`:

```text
for N in 1000 10000 100000:
  create one source, model, ready archive and N ArchiveEntry rows
  GET /api/models/{model_id} as a user with archives.view_entries
  report len(response.content), perf_counter(), tracemalloc peak
```

The exact seed used `path=f"folder-{i // 1000:03}/file-{i:06}.stl"`, a numeric
size, and `modified_at="2026-01-01"`. Startup may log the known empty temporary
database backup-scheduler warning; it is outside the measured request.

## Browsing model and target API

The detail endpoint will retain archive metadata and add `entries_url`, but will
not query or embed `entries` in its steady-state response:

```json
{
  "id": 15,
  "filename": "model.7z",
  "entry_count": 84231,
  "entries_url": "/api/models/9/archives/15/entries"
}
```

The target endpoint is:

```text
GET /api/models/{model_id}/archives/{archive_id}/entries
  ?parent_path=
  &search=
  &cursor=
  &page_size=200
```

`model_id` and `archive_id` must match. The server first resolves the visible
model using the existing source scope, then its archive; a hidden/revoked source
or mismatched archive is `404`. `archives.view_entries` is independently
required (`403` after a visible object has been established, matching current
route conventions). Download permission is not implied or checked by this
listing endpoint.

Normal browse mode has `search` absent and returns **direct children only** of
the canonical `parent_path` (`""` for root). Directories precede files; within a
kind ordering is `name_sort_key ASC, path ASC`. `name_sort_key` is Unicode
`casefold()` computed by Meshive, rather than SQLite `NOCASE`, to make ordering
stable for non-ASCII filenames. The cursor is an opaque, versioned URL-safe
encoding of `{archive_id,parent_path,is_directory,name_sort_key,path}` and is
rejected if it does not match the request context. It is a continuation of that
exact sort order, never an offset.

Search mode has a non-empty `search`, ignores `parent_path`, and searches path
and filename only inside the selected archive. It returns matching full paths,
not a flattened substitute for browse mode. Its cursor contains
`{archive_id,query_version,path_sort_key,path}` and the stable result order is
`path_sort_key ASC, path ASC`. The server defaults `page_size` to 200, permits
1–500, fetches one extra row to determine `next_cursor`, and returns:

```json
{
  "items": [
    {
      "path": "STL/parts/body.stl",
      "name": "body.stl",
      "is_directory": false,
      "size_bytes": 123,
      "compressed_size_bytes": 45,
      "modified_at": "2026-01-01"
    }
  ],
  "next_cursor": null,
  "parent_path": "STL/parts",
  "total": null
}
```

`total` is deliberately `null`: an exact count would add a potentially costly
second operation and is not required for paging. A future estimate must be
explicitly labelled as such.

## Proposed derived schema, query plans, and costs

Add an `archive_browse_nodes` table rather than altering the meaning of
`archive_entries`:

```text
id, archive_id FK, path, parent_path, name,
name_sort_key, path_sort_key, depth, is_directory,
archive_entry_id nullable FK, size_bytes, compressed_size_bytes, modified_at
UNIQUE (archive_id, path)
INDEX (archive_id, parent_path, is_directory DESC, name_sort_key, path)
```

`archive_entry_id` is set for physical rows and null for synthetic directories.
The `archive_entry_search` FTS5 table contains `archive_id UNINDEXED`, `node_id
UNINDEXED`, `path`, and `name` using `unicode61`. It indexes physical nodes and
synthetic directories; search therefore finds a directory by name and a file by
path without reading archive files.

The following `EXPLAIN QUERY PLAN` was run against an in-memory SQLite schema
with exactly these indexes:

```text
root direct children
SEARCH archive_browse_nodes USING INDEX archive_browse_nodes_children
  (archive_id=? AND parent_path=?)

nested folder after a directory cursor
SEARCH archive_browse_nodes USING INDEX archive_browse_nodes_children
  (archive_id=? AND parent_path=? AND is_directory<?)

FTS search
SCAN s VIRTUAL TABLE INDEX 0:M4
SEARCH n USING INTEGER PRIMARY KEY (rowid=?)
USE TEMP B-TREE FOR ORDER BY
```

The first two plans are range/index scans limited to one folder. FTS confines
the search to matching tokens, then joins nodes by primary key. SQLite sorts
matching search results in a temporary B-tree to enforce the stable full-path
order; this is database work, not an unbounded Python list. P4 must benchmark
high-match searches and impose a documented query-length/term policy before
claiming a search latency SLO.

Migration creates the two derived tables and indexes without rewriting physical
entries. A resumable backfill processes one archive at a time with keyset reads
of physical `ArchiveEntry.id` (for example, 1,000 rows), inserts every parent
with `INSERT OR IGNORE`, and commits batches. It must not hold a per-library or
million-entry Python list. The number of browse nodes is physical entries plus
distinct path prefixes, so disk/index cost can materially exceed the current
table for deeply nested archives. Record per-archive index state (`pending`,
`ready`, `failed`) and show an explicit indexing state, never an empty tree, for
unbackfilled archives.

On rescan, the scanner continues to replace physical `ArchiveEntry` rows as it
does today, and replaces all derived browse nodes and FTS rows for that archive
in the same logical refresh. `Archive.entry_count` remains the count reported by
the archive listing, not the number of browse nodes. A failed listing must leave
no stale derived tree advertised as current.

## Scanner, rules, images, access, and frontend

The scanner currently calls `list_archive`, persists physical `ArchiveEntry`
rows, and derives `entry_count` and uncompressed size from non-directory
entries. The derived index is a post-listing projection only. Archive image
selection (`archive_images.py`) and automatic-tag evaluation (`services/tags.py`
and canonical tag-assignment rules) continue to read physical `ArchiveEntry`
rows only; synthetic folders must never become image candidates, tag matches, or
automatic-tag evidence. Their streaming/batched query behaviour is unchanged.

The P4 frontend keeps the present archive tabs and expandable tree. It replaces
the one complete `entries` array with:

- a per-archive, per-parent page cache, retaining loaded children while a folder
  is collapsed or revisited;
- a separate `AbortController` and generation key for entry browse and search,
  following P3; changing archive, folder, query, or unmount aborts the old one;
- a 250 ms debounced search. Search renders full paths and a visible “Back to
  tree” action; choosing a result loads its ancestor chain and expands it in
  normal browse mode;
- explicit initial-folder/loading-more, empty-folder/no-results, access-denied,
  indexing, and retryable-error states. A failed or aborted request must not
  clear a previously cached folder.

All Library Sources stay read-only. This design operates exclusively on Meshive
SQLite data and never lists, extracts, creates, moves, or changes source files.

## Compatibility, risks, and recommendation

P4 must ship backend and frontend together in the single Meshive runtime image.
During implementation, add `entries_url` first and keep a temporary explicit
capability/version field while the new tree client is introduced; do not return
an empty legacy `entries` array that makes an older client silently look like an
archive has no contents. Once every supported client uses the lazy endpoint,
remove the legacy embedded array and its detail-endpoint query in the same
release. Existing data remains readable during backfill via an explicit
“indexing archive contents” state; source revocation cancels/invalidates cached
results and the next request receives `404`.

Risks are FTS database growth, backfill duration and interruption recovery,
Unicode/path canonicalisation, high-match FTS sort cost, stale nodes after a
rescan, and UI complexity around partial folders. Required implementation gates
are a migration/backfill rehearsal on a production-sized copy, query-plan and
search benchmarks, source-revocation tests, scanner cleanup tests, and
Playwright coverage for expand, paginate, search, archive switch, abort, and
returning from search.

**Recommendation:** proceed with P4 only as the derived-node design above. The
current measured payload and memory growth justify it. Do not proceed with
flat offset pagination or a frontend-only filter: either would lose implied
folders or retain the current unbounded transfer.

## Phase 1 implementation boundary

Phase 1 introduces only `archive_browse_nodes`, its child-order index, the
bounded Alembic backfill, and scanner/rescan maintenance. It deliberately adds
no public entries endpoint and does not change the detail payload or tree UI.
The migration is safe to rerun after interruption because every derived row is
unique by `(archive_id, path)` and physical rows upsert that projection. It is
also intentionally a derived-data boundary: downgrade drops browse nodes and
their index but never changes `ArchiveEntry`, archives, sources, tags, images,
or source files. Re-upgrade deterministically rebuilds the projection from the
unchanged physical entries. This is a rollback limitation rather than data
loss: a downgraded runtime has no browse-node table, while all authoritative
archive-listing data remains available for a future upgrade.
