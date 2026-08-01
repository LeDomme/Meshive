# Security policy

## Supported versions

Security fixes are provided for the latest Meshive 1.x release. Operators
should update to the newest patch release before reporting an issue that may
already have been fixed.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting feature on the Meshive repository, or privately open a
draft security advisory for the maintainers.

Include the affected version, deployment conditions, reproduction steps,
impact, and any suggested mitigation. Remove credentials, model files, archive
contents, hostnames, and other private library data from the report.

The project aims to acknowledge a complete report within seven days. A fix and
release schedule depends on severity and complexity. Please allow time for a
coordinated release before publishing details.

## Deployment responsibility

Meshive must be exposed through HTTPS, source libraries must be mounted
read-only, and `/app/data` must remain private and writable only by the Meshive
runtime identity. Administrators are responsible for access to the host,
container-management interface, reverse proxy, container registry, and backup
storage.
