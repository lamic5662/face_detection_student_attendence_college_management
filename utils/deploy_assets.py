from __future__ import annotations

from pathlib import Path


def _replace_line(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f'{key}='
    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            updated.append(f'{prefix}{value}')
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f'{prefix}{value}')
    return updated


def render_env_example(
    template_text: str,
    *,
    public_host: str,
    root_domain: str,
    app_root: str,
    db_name: str = 'smart_attendance',
) -> str:
    shared_root = f'{app_root}/shared'
    current_root = f'{app_root}/current'
    lines = template_text.splitlines()

    replacements = {
        'FLASK_ENV': 'production',
        'ALLOWED_HOSTS': f'localhost,127.0.0.1,.{root_domain}',
        'DEFAULT_COLLEGE_CODE': 'MAIN',
        'MULTI_COLLEGE_ROOT_DOMAIN': root_domain,
        'PUBLIC_BASE_URL': f'https://{public_host}',
        'DB_NAME': db_name,
        'UPLOAD_FOLDER': f'{current_root}/static/uploads/faces',
        'PRIVATE_UPLOAD_FOLDER': f'{shared_root}/uploads',
        'CONTENT_UPLOAD_FOLDER': f'{shared_root}/uploads/content',
        'LIBRARY_UPLOAD_FOLDER': f'{shared_root}/uploads/library',
        'ASSIGNMENT_UPLOAD_FOLDER': f'{shared_root}/uploads/assignment_submissions',
        'LOG_DIR': f'{shared_root}/logs',
        'FORWARDED_ALLOW_IPS': '127.0.0.1',
    }

    for key, value in replacements.items():
        lines = _replace_line(lines, key, value)

    return '\n'.join(lines).rstrip() + '\n'


def render_nginx_conf(
    template_text: str,
    *,
    public_host: str,
    root_domain: str,
    app_root: str,
) -> str:
    return (
        template_text
        .replace('app.example.com', public_host)
        .replace('*.example.com', f'*.{root_domain}')
        .replace('/opt/smart_attendance/current', f'{app_root}/current')
    )


def render_systemd_service(
    template_text: str,
    *,
    app_root: str,
    service_user: str,
    service_group: str,
) -> str:
    return (
        template_text
        .replace('/opt/smart_attendance', app_root)
        .replace('User=www-data', f'User={service_user}')
        .replace('Group=www-data', f'Group={service_group}')
    )


def render_deployment_readme(
    *,
    public_host: str,
    root_domain: str,
    app_root: str,
    service_user: str,
    output_dir: str,
) -> str:
    return f"""# SmartAttend Deployment Bundle

This folder contains deployment-ready files generated for your environment.

## Target

- Public host: `{public_host}`
- Root domain: `{root_domain}`
- App root: `{app_root}`
- Service user: `{service_user}`

## Files

- `.env.production`
- `smart_attendance.conf`
- `smart_attendance.service`
- `smart_attendance@.service`

## Next Steps

1. Copy `.env.production` to `{app_root}/shared/.env` and fill in the secrets.
2. Put the app code at `{app_root}/current`.
3. Create the virtualenv at `{app_root}/venv` and install `requirements.txt`.
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

Generated in: `{output_dir}`
"""


def write_deployment_bundle(
    output_dir: Path,
    *,
    env_example_text: str,
    nginx_template_text: str,
    service_template_text: str,
    service_instance_template_text: str,
    public_host: str,
    root_domain: str,
    app_root: str,
    service_user: str,
    service_group: str,
    db_name: str = 'smart_attendance',
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {
        '.env.production': render_env_example(
            env_example_text,
            public_host=public_host,
            root_domain=root_domain,
            app_root=app_root,
            db_name=db_name,
        ),
        'smart_attendance.conf': render_nginx_conf(
            nginx_template_text,
            public_host=public_host,
            root_domain=root_domain,
            app_root=app_root,
        ),
        'smart_attendance.service': render_systemd_service(
            service_template_text,
            app_root=app_root,
            service_user=service_user,
            service_group=service_group,
        ),
        'smart_attendance@.service': render_systemd_service(
            service_instance_template_text,
            app_root=app_root,
            service_user=service_user,
            service_group=service_group,
        ),
        'DEPLOYMENT.md': render_deployment_readme(
            public_host=public_host,
            root_domain=root_domain,
            app_root=app_root,
            service_user=service_user,
            output_dir=str(output_dir),
        ),
    }

    written: list[Path] = []
    for name, content in files.items():
        path = output_dir / name
        path.write_text(content, encoding='utf-8')
        written.append(path)
    return written
