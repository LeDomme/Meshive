# Backup and restore

Meshive's irreplaceable state is the SQLite database: users, source
configuration, tags, folder rules, scan metadata, and the catalogue. The model
library is mounted read-only and is not part of a Meshive backup. Thumbnails are
also excluded because a source rescan can regenerate them.

## Recommended backup mount

Mount a host, NFS, or other independently backed-up directory into the
container:

```yaml
volumes:
  - meshive-data:/app/data
  - meshive-cache:/app/cache
  - /mnt/backups/meshive:/backups
```

The local-development Compose file creates a separate `meshive-backups` volume.
The production Compose deployment expects `MESHIVE_BACKUP_VOLUME` to refer to
an external volume so removing the application deployment cannot remove it.
For protection against loss of the Docker host, use an NFS volume or another
independently backed-up target.

## Automatic backups

Administrators configure automatic backups at `/admin/backups`:

- daily or weekly frequency;
- local time and IANA timezone, for example `Europe/Berlin`;
- maximum age in days;
- maximum number of automatic backups.

The scheduler runs inside the single Meshive application process. Backup
history records success, failure, size, and destination. **Backup now** creates
a manual backup immediately. Automatic retention never removes manual backups.

Each new backup is one ZIP file containing the consistent `meshive.sqlite3`
snapshot and its checksum manifest. The temporary SQLite snapshot is created
below `/app/data/tmp` and removed automatically after packaging, including when
backup creation fails. Only the finished ZIP is retained below `/backups`.

Backups are organized by type below `MESHIVE_BACKUP_DIR`:

- `scheduled/` for automatic backups;
- `manual/` for backups created on demand;
- `pre-restore/` for safety backups created immediately before a restore.

A backup inside the Meshive data volume survives image updates, but it is not
independent from that volume and should not be the only copy.

## Restore from the web interface

Administrators can select **Restore** beside a completed backup and confirm the
operation by entering `RESTORE`. Meshive validates the backup, stores a restore
request in its data volume, and shuts down cleanly. On the next container start,
the entrypoint restores the database before applying migrations.

The container must use a restart policy such as `restart: unless-stopped`.
During the restart, the page waits for Meshive to become available again and
then displays the restore result. Before replacing the database, Meshive creates
a `pre-restore/pre-restore-*.zip` safety backup below the directory configured
by `MESHIVE_BACKUP_DIR`.

Restoring also restores users, passwords, source configuration, tags, and the
catalogue to the selected point in time. Model files below `/models` are never
changed.

## Online backup from the container host

The regular container may keep running. Execute the command as the configured
application identity. These commands use `compose.yaml`; add
`-f compose.traefik.yaml` after `docker compose` when using the Traefik example:

```sh
docker compose exec meshive \
  sh -lc 'gosu "$PUID:$PGID" meshive backup --output /backups/meshive.zip'
```

Omit `--output` to create a timestamped ZIP in the `manual/` directory below
`MESHIVE_BACKUP_DIR`. The ZIP contains the consistent SQLite database and a
manifest with timestamp, size, and SHA-256 checksum.

Use unique or timestamped filenames in scheduled jobs rather than overwriting
the only known-good backup.

## Restore with Docker Compose

Restore must never run alongside the regular Meshive application.

1. Stop the regular Meshive container:

   ```sh
   docker compose stop meshive
   ```

2. Run a one-off container from the same Compose service and image:

   ```sh
   docker compose run --rm --no-deps meshive \
     meshive restore --input /backups/manual/meshive.zip --confirm-stopped
   ```

3. Verify that the restore container exits successfully, then restart Meshive:

   ```sh
   docker compose start meshive
   ```

The same procedure can be performed through any container-management UI by
stopping the application and starting a temporary container with the identical
image, data volume, backup volume, `PUID`, and `PGID`.

The restore validates the manifest checksum when present, runs SQLite's
integrity check, verifies core Meshive tables, and creates a timestamped
`pre-restore/pre-restore-*.zip` safety backup before replacing the live database.
Existing legacy `.sqlite3` backups with neighboring manifests remain supported.
The normal container applies any newer database migrations when it starts.

Before extracting a ZIP, Meshive verifies its exact member structure, bounds
the manifest size, compares the database size in the manifest and ZIP metadata,
and checks available working space. Extraction itself is byte-limited. The
default maximum SQLite database size accepted for backup and restore is 5 GiB
(`MESHIVE_BACKUP_MAX_RESTORE_BYTES=5368709120`). Meshive also keeps a 64 MiB
free-space reserve (`MESHIVE_BACKUP_RESTORE_MIN_FREE_BYTES=67108864`) in
addition to the temporary database copies required by the operation. These
limits concern only Meshive's SQLite database, never the model library.

## Recovery test

Periodically test a backup against a separate temporary Meshive data volume.
A backup that has never been restored should not be treated as verified.
