# Automatic source scans

Automatic scans are configured separately for each library source under
**Administration → Sources → Edit → Automatic scanning**.

Available schedules:

- **Hourly:** runs at the selected minute of every hour. The hour shown in the
  time input is ignored.
- **Daily:** runs once per day at the selected local time.
- **Weekly:** runs on the selected weekday and local time.

Times use the configured IANA timezone, for example `Europe/Berlin`. Automatic
scanning also requires the source to be active and **Scanning enabled** to be
selected.

Meshive records whether a scan was started manually or by the scheduler. It
never creates a second queue entry while the same source is already queued or
being scanned. Scans above the configured concurrency limit remain in a
persistent first-in, first-out queue. The source administration page displays
running scans and queue positions. If the container was offline at the
scheduled time, one missed scan is queued after Meshive becomes available
again.

The scheduler uses periodic checks rather than filesystem notifications. This
works reliably with local directories as well as Docker-mounted NFS and SMB
storage.

## Manual scan modes

- **Incremental:** enumerates the source, processes new models, and marks known
  models as seen without reparsing them.
- **Full:** parses every discovered model and reconciles archive images while
  reusing current cached derivatives.
- **Full missing-images:** performs a full metadata scan and repairs models
  whose archive-image gallery is incomplete.
- **Reconcile images:** uses the stored archive manifest to repair missing or
  stale derived images without reparsing library metadata.

Targeted **Rescan model** and **Rebuild model images** operations are limited to
that model. The latter intentionally regenerates its archive-derived images.
