# Automatic tagging

Administrators can derive tags from archive contents without extracting whole
archives or changing library files. Create the target tag first, then open
**Administration → Tags → Automatic tag rules**.

Each rule contains:

- text to match;
- the tag to assign; and
- an enabled state.

Matching is a case-insensitive substring comparison against both an archive
entry's name and its full path inside the archive. A rule for `Bust`, for
example, matches `Bust/model.stl`, `parts/bust_supported.stl`, and equivalent
capitalisation. Every configured archive belonging to a model is considered.
Regular expressions are intentionally not supported in this release.

Creating, editing, enabling, disabling, or deleting a rule immediately
re-evaluates existing indexed models. **Re-evaluate all models** is available
for an explicit repeat after maintenance or troubleshooting. Normal source
scans also evaluate every scanned model and report the number of matches and
assignment changes in the scan summary.

Meshive records automatic provenance independently from direct and inherited
folder tags. If the same tag was also assigned manually or inherited from a
folder rule, removing an automatic match does not remove those other
assignments. Repeated scans and re-evaluations are idempotent.

Rules, match provenance, and derived assignments are stored in Meshive's
SQLite database and are therefore included in normal backups. The mounted
model library remains read-only.

## Canonical tag-assignment rules

Current tag administration uses **Tag assignment rules** as the canonical rule
system. A rule belongs to one tag, may be limited to a library source or apply
to all sources, and contains one or more configured targets. Administrators can
preview the matching models before saving, then re-evaluate one rule or all
rules after maintenance. Rule changes reconcile only Meshive's database tag
assignments; they never alter an archive, image, folder, or other source file.

The legacy folder and automatic-rule endpoints are retained only as read-only
migration compatibility surfaces. Create and maintain new rules through the
canonical assignment-rule interface.
