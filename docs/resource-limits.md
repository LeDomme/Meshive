# Resource and concurrency limits

Meshive applies conservative application-level concurrency limits so large
libraries and archive downloads do not overload a Docker host or network
storage.

## Source scans

`MESHIVE_MAX_CONCURRENT_SCANS` controls how many library sources may be scanned
at the same time. The default is `1`. This is recommended for NFS and other
shared storage because archive listing and thumbnail generation can create
substantial random I/O.

If all scan slots are occupied, manual and scheduled scans enter a persistent
first-in, first-out queue. A new scan for a source that is already queued or
running returns HTTP 409 instead of creating a duplicate. The next queued scan
starts immediately when capacity becomes available.

Scans that were running when the application stopped are marked as failed
during the next startup. Pending queue entries are retained and continue after
the restart.

## Archive inspection

`MESHIVE_ARCHIVE_TIMEOUT_SECONDS` defaults to 120 seconds and
`MESHIVE_ARCHIVE_MAX_ENTRIES` defaults to 100,000 entries.
`MESHIVE_ARCHIVE_MAX_OUTPUT_BYTES` additionally limits the raw output read from
7-Zip and defaults to `67108864` bytes (64 MiB). Meshive terminates the archive
process as soon as a limit is exceeded, rather than first collecting unbounded
output in application memory.

This limit only applies to the textual archive-content listing. It does not
limit archive file sizes or authenticated downloads.

## Images from archives

Archive-image candidate discovery is bounded before extraction begins. The
defaults allow at most 48 candidates, 64 MiB declared uncompressed and
compressed size per entry, and 256 MiB declared uncompressed size in total per
model. Decoded images are limited to 100 megapixels, and an archive-image
7-Zip extraction has a 90-second deadline. Image decoding remains bounded by
the extracted-byte and pixel limits.

The settings are documented together with the deterministic selection rules in
[Images from archives](archive-images.md). Nested archives are never inspected
for images, and generated WebP files are stored only in Meshive's writable
cache.

All catalogue thumbnails, whether derived from a folder image or an archive
image, are capped at `MESHIVE_THUMBNAIL_MAX_BYTES`. The default is 65536 bytes
(64 KiB). Meshive lowers WebP quality and, for complex images, dimensions
until the hard byte limit is met. `MESHIVE_THUMBNAIL_SIZE` remains the maximum
edge length and never forces an image to be enlarged.

## Archive downloads

`MESHIVE_MAX_CONCURRENT_DOWNLOADS` controls the number of archive responses
that may be streamed concurrently. The default is `4`. When the limit is
reached, Meshive returns HTTP 429 with a `Retry-After` header instead of opening
another potentially long-running file stream.

For models with multiple archives, **Download all archives** streams one
uncompressed TAR containing the original archive files. This consumes one
download slot and uses no temporary bundle file or archive recompression.
Individual archive downloads retain HTTP range support; the generated TAR
stream does not support resuming with a range request.

These limits apply to the single Meshive runtime process used by the supported
deployment. Example Compose configuration:

```yaml
environment:
  MESHIVE_MAX_CONCURRENT_SCANS: 1
  MESHIVE_MAX_CONCURRENT_DOWNLOADS: 4
  MESHIVE_ARCHIVE_TIMEOUT_SECONDS: 120
  MESHIVE_ARCHIVE_MAX_ENTRIES: 100000
  MESHIVE_ARCHIVE_MAX_OUTPUT_BYTES: 67108864
  MESHIVE_ARCHIVE_IMAGE_MAX_CANDIDATES: 48
  MESHIVE_ARCHIVE_IMAGE_MAX_ENTRY_BYTES: 67108864
  MESHIVE_ARCHIVE_IMAGE_MAX_COMPRESSED_BYTES: 67108864
  MESHIVE_ARCHIVE_IMAGE_MAX_TOTAL_BYTES: 268435456
  MESHIVE_ARCHIVE_IMAGE_MAX_PIXELS: 100000000
  MESHIVE_ARCHIVE_IMAGE_TIMEOUT_SECONDS: 90
  MESHIVE_ARCHIVE_IMAGE_THREADS: 1
  MESHIVE_ARCHIVE_IMAGE_DETAIL_SIZE: 1600
  MESHIVE_ARCHIVE_IMAGE_DETAIL_MAX_BYTES: 393216
  MESHIVE_ARCHIVE_IMAGE_WEBP_METHOD: 4
  MESHIVE_THUMBNAIL_MAX_BYTES: 65536
```

Increase the values gradually and observe CPU, memory, disk, and network usage.
