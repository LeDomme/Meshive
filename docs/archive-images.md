# Images from archives

Meshive 1.4 introduces bounded extraction of gallery images from 7z, ZIP, and
RAR model archives. The source archives and model directories remain read-only;
all derived images are written only to Meshive's cache volume.

## Selection rules

The initial supported embedded formats are JPEG, PNG, and WebP. Candidate
matching is case-insensitive. Meshive does not recurse into nested archives and
does not treat files below hidden system folders, `__MACOSX`, texture, material,
or map directories as gallery images.

Candidate order is deterministic. Filenames containing `cover`, `preview`,
`render`, `promo`, `beauty`, or `thumbnail` are preferred in that order,
followed by shallower paths and a case-insensitive path sort. This makes repeat
scans stable without relying on archive entry order.

Valid archive images take precedence for the catalogue and model gallery.
Existing images beside an archive remain indexed
as a fallback when an archive contains no usable image or processing fails.
Meshive never removes or changes those source images.

### Successful-image limit and backfill

Selection first creates a deterministic candidate pool for every ready archive,
then sorts that combined pool by image priority, archive filename, and archive
path. Consequently, adding another archive does not depend on filesystem
enumeration order.

The configured candidate limit is the number of successful archive images that
may remain in the gallery. To avoid losing the gallery when an otherwise
well-ranked entry is corrupt or cannot be converted, Meshive may attempt up to
four times that limit while still enforcing the configured total extraction
budget. Failed validation, extraction, or derivative generation simply allows
a later candidate to backfill the result.

After processing, Meshive deterministically keeps only the first configured
number of successful images and removes any surplus derived records. Valid candidates
skipped by candidate, per-entry size, compressed size, or total extraction
budget create exactly one admin scan issue per model: archive_image_candidates_skipped
at warning severity. Hidden, invalid, texture, material, map, decal, and
similar paths remain intentionally silent. The bounded candidate pool prevents
large archives from crowding out scan resources; entries beyond the pool are not extracted for backfill.
## Resource limits

Selection and processing use conservative defaults:

| Environment variable | Default | Purpose |
| --- | ---: | --- |
| `MESHIVE_ARCHIVE_IMAGE_MAX_CANDIDATES` | `48` | Maximum selected images per model |
| `MESHIVE_ARCHIVE_IMAGE_MAX_ENTRY_BYTES` | `67108864` | Maximum declared uncompressed size per image |
| `MESHIVE_ARCHIVE_IMAGE_MAX_COMPRESSED_BYTES` | `67108864` | Maximum declared compressed size per image |
| `MESHIVE_ARCHIVE_IMAGE_MAX_TOTAL_BYTES` | `268435456` | Maximum declared total size selected per model |
| `MESHIVE_ARCHIVE_IMAGE_MAX_PIXELS` | `100000000` | Maximum decoded pixel count per image |
| `MESHIVE_ARCHIVE_IMAGE_TIMEOUT_SECONDS` | `90` | Processing deadline for one bounded archive-image batch |
| `MESHIVE_ARCHIVE_IMAGE_THREADS` | `1` | 7-Zip threads used only while extracting an archive image |
| `MESHIVE_ARCHIVE_IMAGE_DETAIL_SIZE` | `1600` | Maximum edge length of the full archive-image gallery variant |
| `MESHIVE_ARCHIVE_IMAGE_DETAIL_MAX_BYTES` | `393216` | Hard byte limit for the full archive-image gallery variant |
| `MESHIVE_ARCHIVE_IMAGE_WEBP_METHOD` | `4` | WebP encoder effort for archive-image variants, from 0 (fastest) to 6 (smallest/slowest) |

Entries without a declared uncompressed size are skipped. Some solid archives
do not expose a useful compressed size for every entry; in that case the
compressed-size filter is best effort while the uncompressed output limit
remains mandatory. Image bytes will also be validated by Pillow independently
of their filename extension before they are accepted.

Selected entries are extracted one at a time through 7-Zip's standard output;
the command is invoked without a shell and is terminated as soon as its time or
byte budget is exceeded. Wildcards, listfile syntax, control characters, and
nested archive traversal are rejected. The temporary file exists only below
`MESHIVE_DATA_DIR/tmp/archive-images` for the duration of validation and is
removed on success or failure.

Pillow detects the actual image format from its contents, verifies the file,
fully decodes it, and checks its pixel count before any cached derivative is
created. A filename ending in `.jpg` therefore cannot make arbitrary or broken
data pass validation; a valid supported image with a mismatched extension can
still be identified by its real content.

The limits cover candidate selection and the bounded extraction pipeline. They
do not restrict authenticated downloads of the original archive.

For every accepted archive image, Meshive creates a full WebP gallery variant
and a catalogue thumbnail in its writable cache. The full variant is limited
to 1600 pixels on its longest edge and 384 KiB by default; the thumbnail stays
limited to 64 KiB. Archive images are never extracted into the source mount
and their temporary extraction files are deleted after processing.
Archive-image extraction deliberately uses a single 7-Zip thread by default so
scans remain responsive for web requests. Increase `MESHIVE_ARCHIVE_IMAGE_THREADS`
only if the host has spare capacity and faster scans are more important than
interactive responsiveness.

Catalogue thumbnails use the shared Meshive thumbnail pipeline and are hard
limited to `MESHIVE_THUMBNAIL_MAX_BYTES`, which defaults to 65536 bytes
(64 KiB). Encoding first reduces WebP quality and then image dimensions as
needed. The configured maximum dimensions and byte limit are both included in
the cache signature, so changing either setting produces a fresh derivative.
