# SmartAttend Deployment Bundle

This folder contains deployment-ready files generated for your environment.

## Target

- Public host: `suraj57.com.np`
- Root domain: `suraj57.com.np`
- App root: `/opt/smart_attendance`
- Service user: `www-data`

## Files

- `.env.production`
- `smart_attendance.conf`
- `smart_attendance.service`
- `smart_attendance@.service`

## Next Steps

1. Copy `.env.production` to `/opt/smart_attendance/shared/.env` and fill in the secrets.
2. Put the app code at `/opt/smart_attendance/current`.
3. Create the virtualenv at `/opt/smart_attendance/venv` and install `requirements.txt`.
4. Copy `smart_attendance.conf` into your Nginx sites directory.
5. Copy the systemd files into `/etc/systemd/system/`.
6. Run:

```bash
flask --app run.py db upgrade
flask --app run.py doctor
```

7. Start the service instances:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now smart_attendance@5050
sudo systemctl enable --now smart_attendance@5051
sudo nginx -t
sudo systemctl reload nginx
```

Generated in: `/Users/surajlamichhane/Desktop/smart_attendance/deploy/generated`
