# Release checklist

Use this checklist for every stable Meshive release.

## Prepare

- Update the backend and frontend versions to the same semantic version.
- Update `CHANGELOG.md` and any changed configuration in `.env.example`.
- Review database migrations and document incompatible rollback conditions.
- Build the frontend and run the complete backend test suite.
- Run the Playwright suite; it is a required GitHub Actions check.
- Run dependency audits and the database migration test.
- Validate both Compose examples and confirm the development-plan file is not
  tracked.
- Build the runtime image and verify its health check.
- Confirm the release documentation states that library-source files and
  folders are never modified, and that a validated database backup is required
  before production deployment.
- Confirm the audit-retention and session-revocation limitations remain
  documented accurately.

## Acceptance test

- Sign in as an administrator and a normal user.
- Scan representative 7z, ZIP, and RAR sources twice.
- Verify thumbnails, gallery filters, detail pages, and archive trees.
- Download one archive with a range request and one multi-archive bundle.
- Create, validate, and restore a manual backup; verify the pre-restore backup.
- Confirm scheduled scans and scheduled backups run after a restart.
- Confirm the model mounts are read-only and the browser console has no
  application-generated CSP errors.
- For scan-related releases, verify the configured-source default, an explicit
  alternative scan mode, and live scan activity through completion.
- For diagnostics changes, confirm large or network-backed storage is checked
  promptly and no probe file remains after refresh.

## Publish

1. Merge the release commit into `main` and wait for a green workflow.
2. Create an annotated `vX.Y.Z` tag on that exact commit.
3. Push the tag. CI publishes semantic GHCR tags, an SBOM/provenance
   attestation, and the GitHub Release.
4. Deploy the immutable version tag and complete the production smoke test.
5. Confirm the release notes, semantic image tags, `latest`, and image digest
   are visible. The `edge` tag must remain the development channel from `main`.

## Pull request validation image
For each pull request that needs a deployment test, run the Build and publish container workflow manually on the branch.
It publishes ghcr.io/ledomme/meshive:sha-SHORTSHA and smoke-tests that exact image. PR branches do not publish edge tags.
Deploy that SHA tag in Portainer for the manual validation, then record the result on the pull request.
## Rollback readiness

- Keep the previous image digest and a validated pre-upgrade database backup.
- Do not run an older image against a schema it does not support.
- Record any restore or rollback performed during the release.
