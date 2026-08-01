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
```

Increase the values gradually and observe CPU, memory, disk, and network usage.
