# Audit log

Users with `audit.view` and effective all-sources access can open
**Administration → Audit log**. The log is intentionally an all-sources
administrative record rather than a source-scoped catalogue view.

Filter events by action, actor, and inclusive From and To timestamps. **Export
CSV** applies the same filters and produces UTF-8 CSV with four safe columns:
timestamp, actor, event, and target. Exports contain at most 10,000 events; a
final truncation row is included when more matching events exist. Meshive may
record one `audit.exported` event for an accepted export without recording the
filter values or export contents.

## Covered actions

Accepted administrative actions are audited for role and user management,
library-source changes, scan starts and controls, backup creation, deletion,
and restore lifecycle, metadata and tag changes, canonical tag-assignment-rule
changes, and direct model actions such as selecting a primary image, adding or
removing a direct tag, queueing a rescan or image rebuild, resetting images,
and deleting missing models. Events are written only for successful or accepted
actions; denied, hidden, missing, and failed actions do not create an event.

Audit records contain safe action snapshots and may associate an event with a
library source. They do not store source paths, file or image names, tag names,
request payloads, error text, secrets, CSV filters, or CSV contents.

## Retention

Audit retention is currently unlimited. Meshive has no automatic audit cleanup
and no audit-event deletion feature. Size and retention planning for the SQLite
database and its backups is therefore the deployment operator's responsibility.
