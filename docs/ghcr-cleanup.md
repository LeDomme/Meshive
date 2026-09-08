# GHCR cleanup

`Cleanup GHCR images` runs daily and can be run manually from **Actions**. Its
manual default is a dry-run; select `dry_run: false` only after reviewing the
candidate list. Scheduled runs are dry-runs until the repository variable
`GHCR_CLEANUP_DELETE_ENABLED` is explicitly set to `true`. The safe rollout is:
merge the workflow, run a manual dry-run, review it, optionally perform one
manual real cleanup, then enable scheduled deletion with that variable.

Once enabled, scheduled runs delete only package versions older than seven days
whose tags are exclusively `pr-*` and/or `sha-*`, plus genuinely orphaned
untagged versions of the same age.

`latest`, `edge`, and numeric SemVer tags (`1`, `1.6`, `1.6.4`) are retained.
Unknown tags are retained too. Every tagged root that is not exclusively
`pr-*`/`sha-*` protects its complete OCI graph. The workflow inspects that graph,
including child manifests and `subject` digests. The current Meshive Buildx
provenance/SBOM structure exposes those dependencies through
`docker buildx imagetools inspect --raw`; no unverified OCI Referrers API call
is required.

Discovery is fail-closed: an incomplete Packages API response or required
manifest lookup prevents every deletion. The final version is re-read before a
delete to avoid races with a new release or tag.

The workflow uses only `GITHUB_TOKEN`. In the package's **Settings → Manage
Actions access**, grant `LeDomme/Meshive` **Admin** access to
`ghcr.io/ledomme/meshive`; otherwise the workflow fails without a PAT fallback.
