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

Schedule `backup.sh` nightly. Test a restore on a spare machine before relying on it.

## Scheduled jobs

The `beat` service sends each approver a morning summary at 9:00 (Asia/Kolkata). Run only
one `beat`. Without it, a daily cron job can run
`docker compose exec backend python manage.py send_morning_summary` instead; running both
does no harm, as nobody gets a second summary on the same day.
