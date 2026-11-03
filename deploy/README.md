# Deployment

These files have not been run yet, because the development machine has no Docker.
Try them on a staging server first.

## First time

1. Create the database and roles on the PostgreSQL server, using
   `backend/scripts/bootstrap_db.sql`.
2. Copy `.env.example` to `.env` and fill it in. Keep the keys somewhere safe outside the
   server as well: losing `FIELD_ENCRYPTION_KEYS` loses every document for good.
3. Put the TLS certificate at `$TLS_PATH/fullchain.pem` and `$TLS_PATH/privkey.pem`.
4. Create the media folder, owned by uid 10001:

   ```
   sudo install -d -o 10001 -m 750 /var/lib/member-onboarding/media
   ```

5. Start everything:

   ```
   docker compose up -d --build
   docker compose exec backend python manage.py create_organization \
     --name "Kashee Milk" --slug kashee --admin-email you@example.com
   ```

6. Open `https://<host>/health/ready/` through the backend. It must report `ok`:

   ```
   docker compose exec backend python -c "import urllib.request as u; print(u.urlopen(u.Request('http://127.0.0.1:8000/health/ready/', headers={'Host': 'localhost'})).read())"
   ```

   `unsafe_role` means the app connected as a role that can bypass row level security.

## Updating

```
docker compose up -d --build
```

Migrations and role updates run before the new backend starts.

## Backups

A restore needs three things, kept in three places:

| What | Where it is backed up |
|---|---|
| Database | The DB server's nightly `pg_backup.ps1` (erp_master), which dumps every database as `postgres` |
| Uploaded files | `backup.sh` on the app server, nightly from cron |
| `FIELD_ENCRYPTION_KEYS` | The password manager, never beside the backups |

Every table is row-level secured with FORCE, so `pg_dump` as the owner fails. Dump
as a superuser, or as a role with `BYPASSRLS` (set `BACKUP_DATABASE_URL` for
`backup.sh` to take the dump itself).

On the app server, as root:

```bash
mkdir -p /var/backups/member-onboarding
echo '15 2 * * * root BACKUP_DIR=/var/backups/member-onboarding /opt/member-onboarding/app/deploy/backup.sh' > /etc/cron.d/member-onboarding-backup
```

Set `COPY_TO` (any rsync target) once the NAS is ready, so a copy leaves the machine.

`windows/restore_check.ps1` is the weekly restore drill on the DB server: it restores
the newest dump into a scratch database, logs each organization's counts and drops it.

### One organization

```bash
python manage.py export_organization kashee --out /var/backups/member-onboarding/orgs
```

writes that organization's rows and sealed files to one archive with a manifest of
counts, for handing an organization its records or answering a legal request. To get
one organization back as it was on a given night, restore that night's dump into a
scratch database and export it from there. Loading an archive back into a live
database is not built yet: it needs an import command that writes inside the
organization's context.

## Scheduled jobs

The `beat` service sends each approver a morning summary at 9:00 (Asia/Kolkata). Run only
one `beat`. Without it, a daily cron job can run
`docker compose exec backend python manage.py send_morning_summary` instead; running both
does no harm, as nobody gets a second summary on the same day.
