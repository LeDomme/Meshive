# GHCR cleanup

`Cleanup GHCR images` runs daily and can be run manually from **Actions**. Its
manual default is a dry-run; select `dry_run: false` only after reviewing the
candidate list. Scheduled runs delete only package versions older than seven
days whose tags are exclusively `pr-*` and/or `sha-*`, plus genuinely orphaned
untagged versions of the same age.

`latest`, `edge`, and numeric SemVer tags (`1`, `1.6`, `1.6.4`) are retained.
Unknown tags are retained too. The workflow inspects the protected OCI graph,
including child manifests and OCI referrers used for Buildx provenance/SBOM, so
their untagged package versions are not treated as orphaned.

Discovery is fail-closed: an incomplete Packages API response, manifest, or
referrer lookup prevents every deletion. The final version is re-read before a
delete to avoid races with a new release or tag.

The workflow uses only `GITHUB_TOKEN`. In the package's **Settings → Manage
Actions access**, grant `LeDomme/Meshive` **Admin** access to
`ghcr.io/ledomme/meshive`; otherwise the workflow fails without a PAT fallback.
