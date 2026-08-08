# Images from archives

Meshive 1.3 introduces bounded extraction of gallery images from 7z, ZIP, and
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

Once image extraction is enabled, valid archive images take precedence for the
catalogue and model gallery. Existing images beside an archive remain indexed
as a fallback when an archive contains no usable image or processing fails.
Meshive never removes or changes those source images.

## Resource limits

Selection and processing use conservative defaults:

| Environment variable | Default | Purpose |
| --- | ---: | --- |
| `MESHIVE_ARCHIVE_IMAGE_MAX_CANDIDATES` | `12` | Maximum selected images per model |
| `MESHIVE_ARCHIVE_IMAGE_MAX_ENTRY_BYTES` | `33554432` | Maximum declared uncompressed size per image |
| `MESHIVE_ARCHIVE_IMAGE_MAX_COMPRESSED_BYTES` | `33554432` | Maximum declared compressed size per image |
| `MESHIVE_ARCHIVE_IMAGE_MAX_TOTAL_BYTES` | `134217728` | Maximum declared total size selected per model |
| `MESHIVE_ARCHIVE_IMAGE_MAX_PIXELS` | `40000000` | Maximum decoded pixel count per image |
| `MESHIVE_ARCHIVE_IMAGE_TIMEOUT_SECONDS` | `30` | Processing deadline for an archive-image operation |

Entries without a declared uncompressed size are skipped. Some solid archives
do not expose a useful compressed size for every entry; in that case the
compressed-size filter is best effort while the uncompressed output limit
remains mandatory. Image bytes will also be validated by Pillow independently
of their filename extension before they are accepted.

The limits cover candidate selection and the upcoming extraction pipeline.
They do not restrict authenticated downloads of the original archive.

Catalogue thumbnails use the shared Meshive thumbnail pipeline and are hard
limited to `MESHIVE_THUMBNAIL_MAX_BYTES`, which defaults to 102400 bytes
(100 KiB). Encoding first reduces WebP quality and then image dimensions as
needed. The configured maximum dimensions and byte limit are both included in
the cache signature, so changing either setting produces a fresh derivative.
