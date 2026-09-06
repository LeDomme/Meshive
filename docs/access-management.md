# Access management

Meshive uses local accounts, roles, permission keys, and library-source scopes.
There is no public registration. Administrators create users and assign either
a system role or a custom role.

## Roles and source scopes

The built-in roles are Viewer, Member, Curator, Operator, and Administrator.
Viewer can browse accessible catalogue content; Member additionally downloads
archives; Curator maintains metadata and tags; Operator controls scans and
diagnostics; Administrator has the complete permission set. Custom roles can
combine the same stable permission keys.

A user either has **all sources** access or explicit grants to selected library
sources. A selected-source user can only see and operate models and scans in
those sources. Administration that changes global configuration, roles, users,
audit records, backups, metadata, tags, or canonical tag-assignment rules
requires both its permission and effective all-sources access.

Changing a user's role, active state, password requirement, or source grants
takes effect for future authorization checks. Meshive has no administrator
operation to revoke another user's existing sessions. Because that operation
does not exist, there is no corresponding audit event.

## Library sources and scans

Administrators configure source roots below the approved library root and set
their parsing patterns, supported archive and image formats, and scan settings.
Source management is restricted to users with the appropriate all-sources
permission. Scan controls honor source scopes: a user can only start, inspect,
pause, resume, cancel, or queue targeted work for sources they may access and
for which their role grants the relevant scan permission.

Every configured library source is read-only. Meshive never modifies source
files or folders: it does not upload, rename, move, delete, or permanently
extract library content. Derived thumbnails, archive images, database records,
and backups live outside the source mount.
