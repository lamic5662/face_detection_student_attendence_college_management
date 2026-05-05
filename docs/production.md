# Production Deployment

This app is designed to run behind a reverse proxy with Gunicorn and MySQL. The repo now includes deployment templates under [`deploy/`](../deploy):

- `deploy/nginx/smart_attendance.conf`
- `deploy/systemd/smart_attendance.service`
- `deploy/logrotate/smart_attendance`
- `deploy/backup/backup_example.sh`

## Minimum Stack

- Python 3.12
- MySQL
- Redis for rate limiting
- Gunicorn
- Nginx or Caddy for HTTPS and proxying

## Required Environment

Set at minimum:

- `FLASK_ENV=production`
- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `RATELIMIT_STORAGE_URI`
- `CONTENT_UPLOAD_FOLDER`
- `ASSIGNMENT_UPLOAD_FOLDER`

Use [.env.example](../.env.example) as the base template.

## Reverse Proxy Expectations

The app supports trusted proxy headers through `ProxyFix`.

Recommended values:

- `TRUST_PROXY_HEADERS=True`
- `TRUSTED_PROXY_HOPS=1`

If you serve college portals on subdomains, also set:

- `MULTI_COLLEGE_ROOT_DOMAIN=example.com`

The included Nginx config assumes:

- Gunicorn listens on `127.0.0.1:5050`
- the app code lives at `/opt/smart_attendance/current`
- static files are served from `/opt/smart_attendance/current/static/`
- private uploads remain outside `static/`

## Preflight

Run:

```bash
flask --app run.py db upgrade
flask --app run.py doctor
```

`doctor` fails if:

- the database is unreachable
- `ALLOWED_HOSTS` is empty
- rate limiting still uses `memory://`
- upload folders point into `static/`

## Gunicorn

Start with:

```bash
gunicorn -c gunicorn.conf.py run:app
```

Useful overrides:

- `GUNICORN_WORKERS`
- `GUNICORN_THREADS`
- `GUNICORN_TIMEOUT`
- `GUNICORN_MAX_REQUESTS`
- `GUNICORN_MAX_REQUESTS_JITTER`

## systemd

The included `deploy/systemd/smart_attendance.service` expects:

- app code at `/opt/smart_attendance/current`
- virtualenv at `/opt/smart_attendance/venv`
- shared `.env` at `/opt/smart_attendance/shared/.env`
- logs at `/opt/smart_attendance/shared/logs`
- private uploads at `/opt/smart_attendance/shared/uploads`

After copying it into `/etc/systemd/system/`, run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable smart_attendance
sudo systemctl start smart_attendance
sudo systemctl status smart_attendance
```

## Nginx

Copy the provided config into your Nginx sites directory, replace `example.com`, then validate and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

For HTTPS, terminate TLS in Nginx or Caddy. If you use Certbot, update `server_name` first, then issue the certificate for the root domain and any wildcard/subdomain strategy you plan to use.

## Storage

Keep uploads private:

- content uploads outside `static/`
- assignment submissions outside `static/`

Back up:

- MySQL database
- private upload directories
- `.env` secrets in your secret manager, not in Git

The included `deploy/backup/backup_example.sh` is a simple example that:

- dumps MySQL with `mysqldump`
- archives private uploads
- removes backups older than 14 days

Use cron or a systemd timer to schedule it. Do not rely on it as your only backup plan without testing restore.

## Rollout Checklist

1. Create deploy directories:

```bash
sudo mkdir -p /opt/smart_attendance/{current,shared/uploads,shared/logs,shared/backups}
```

2. Place the app code in `/opt/smart_attendance/current`.
3. Create the virtualenv and install dependencies.
4. Copy `.env.example` to `/opt/smart_attendance/shared/.env` and fill production values.
5. Set private upload paths in `.env` outside `static/`.
6. Run migrations:

```bash
flask --app run.py db upgrade
```

7. Run deployment checks:

```bash
flask --app run.py doctor
```

8. Install and start the systemd service.
9. Install and reload Nginx.
10. Verify:
   - `/health`
   - admin login
   - one student login
   - attachment preview
   - upload flow
   - notice bell updates
   - background alerts / scheduled workflows you rely on

## Monitoring

At minimum, monitor:

- `/health`
- MySQL availability
- Redis availability
- Gunicorn worker restarts
- disk space for uploads and logs

Also monitor:

- 4xx/5xx spikes from Nginx and Gunicorn
- backup success/failure
- upload directory growth
- certificate expiry if TLS is terminated locally
