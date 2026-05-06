# SmartAttend

SmartAttend is a Flask-based college management and smart attendance system built for multi-role campus operations. It combines face-recognition attendance with student, teacher, parent, and admin workflows in one application.

## Main Features

- Face-based attendance with liveness/blink verification
- Multi-college SaaS-ready tenant architecture
- Multi-role login for admin, teacher, student, and parent
- Attendance sessions, live marking, manual overrides, and downloadable reports
- Student face enrollment and profile management
- Teacher content publishing for notes, assignments, labs, and question sets
- Assignment submission, grading, and parent tracking
- In-app preview for notes and supported attachments
- Leave request workflow
- Exam scheduling, marks entry, and printable marksheets
- Fee structures and payment tracking
- Academic calendar with holidays, exam weeks, and event dates
- Parent dashboard with attendance, fees, results, timetable, and location tracking
- Student digital ID card request flow and admin approval
- Real-time notice bell with read/dismiss actions
- Notices, timetable management, analytics, and file management

## Tech Stack

- Python 3.12
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- MySQL with `PyMySQL`
- Flask-Login, Flask-WTF, Flask-Limiter
- OpenCV, `face-recognition`, `dlib`
- Pandas and OpenPyXL for exports

## Project Structure

```text
smart_attendance/
├── app.py
├── run.py
├── config.py
├── routes/
├── models/
├── services/
├── templates/
├── static/
├── migrations/
├── tests/
└── utils/
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and update the values.
4. Make sure MySQL is running and the target database exists.
5. Initialize the database:

```bash
flask --app run.py init-db
```

6. Create an admin account:

```bash
flask --app run.py create-admin
```

7. Start the development server:

```bash
python run.py
```

The app runs by default on `http://127.0.0.1:5050`.

## Environment Notes

Important settings are documented in [.env.example](.env.example).

Key variables:

- `SECRET_KEY`
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`
- `RATELIMIT_STORAGE_URI`
- `CONTENT_UPLOAD_FOLDER`
- `LOW_ATTENDANCE_THRESHOLD`

## CLI Commands

```bash
flask --app run.py init-db
flask --app run.py create-college
flask --app run.py create-admin
flask --app run.py check-classes
flask --app run.py doctor
flask --app run.py tunnel-guide
flask --app run.py start-mobile-tunnel
flask --app run.py mobile-tunnel-status
flask --app run.py stop-mobile-tunnel
flask --app run.py start-local-cluster
flask --app run.py local-cluster-status
flask --app run.py stop-local-cluster
```

`check-classes` sends alerts when a scheduled class has passed and no attendance session was started.
`doctor` runs deployment-readiness checks for database connectivity, host allowlists, limiter backend, and private upload paths.
`tunnel-guide` prints the ngrok steps for mobile password reset testing.
`start-mobile-tunnel` starts a quick Cloudflare tunnel and writes its public URL to `PUBLIC_BASE_URL` in `.env`.
`mobile-tunnel-status` shows the stored tunnel PID, URL, and log path.
`stop-mobile-tunnel` stops the managed Cloudflare tunnel.
`start-local-cluster` starts a local multi-instance Gunicorn cluster for Nginx load balancing.
`local-cluster-status` shows the local Gunicorn cluster state.
`stop-local-cluster` stops the local Gunicorn cluster instances.

## Multi-College Usage

The app supports multiple colleges in one deployment.

- Create each college tenant with `flask --app run.py create-college`
- Create one admin account per college with `flask --app run.py create-admin`
- Users log in with their own `college code` plus email/password
- Each college gets isolated users, notices, attendance, content, fees, exams, ID cards, calendar events, and settings

## Optional File Preview Dependencies

Some in-app attachment previews depend on:

- `python-docx`
- `python-pptx`

These are already listed in [requirements.txt](requirements.txt). If one is missing, the app will still run, but preview support for that file type will be limited.

## Face Recognition Model

The repo currently includes:

- `models_data/shape_predictor_68_face_landmarks.dat`

This file is large and is required for liveness detection. For long-term maintenance, Git LFS or a scripted download step would be a better approach than regular Git tracking.

## Tests

Run the current regression tests with:

```bash
pytest
```

## User Guide

The application includes an in-system user manual available from the sidebar or directly at:

- `/help`

Admins can view the guides for all roles. Other users only see the guide for their own role.

## In-System Setup Flow

Admins now have a built-in production setup flow inside the app:

1. Log in as the college admin.
2. Open `Sidebar -> System Setup`.
3. Finish the readiness checklist:
   - college profile and address
   - map location pin
   - ID card branding
   - departments
   - teachers
   - students
   - subjects
   - production config checks
4. Use `Sidebar -> Settings` for college profile and location.
5. Use `Sidebar -> Digital ID Cards` and `ID Card Template` to prepare official card branding.

The admin dashboard also shows a warning banner until the setup is in a deployable state.

## Production Notes

- Set `FLASK_ENV=production`
- Configure a strong `SECRET_KEY`
- Set `ALLOWED_HOSTS` for your real domains
- Use a shared limiter backend such as Redis via `RATELIMIT_STORAGE_URI`
- Keep `CONTENT_UPLOAD_FOLDER` and `ASSIGNMENT_UPLOAD_FOLDER` outside the public `static` directory
- Put the app behind a reverse proxy and enable `TRUST_PROXY_HEADERS=True`
- Run `flask --app run.py doctor` before deployment
- Do not commit `.env`, runtime logs, or generated uploads
- Consider moving the large dlib model file to Git LFS

For a fuller server rollout guide, see [docs/production.md](docs/production.md).

## Full System Guide

For a complete handbook covering:

- all five user roles
- major platform features
- technology stack
- free tools used in the setup
- first-time installation and onboarding

see [docs/system_guide.md](docs/system_guide.md).

## Mobile Password Reset Testing

If you run SmartAttend locally on your laptop and open Gmail on your phone, password reset links will only work if the link points to a URL your phone can reach.

For local mobile testing:

1. Start the app normally:

```bash
python run.py
```

2. The easiest option is:

```bash
flask --app run.py start-mobile-tunnel
```

This starts a quick Cloudflare tunnel and updates `PUBLIC_BASE_URL` in `.env` automatically.

3. Restart the app.
4. Send the forgot-password email again.

Manual option:

1. Start ngrok:

```bash
ngrok http 5050
```

2. Copy the HTTPS forwarding URL from ngrok.
3. Set `PUBLIC_BASE_URL` in `.env` to that ngrok URL.
4. Restart the app.
5. Send the forgot-password email again.

You can also use:

```bash
flask --app run.py tunnel-guide
```

You can inspect or stop the managed tunnel with:

```bash
flask --app run.py mobile-tunnel-status
flask --app run.py stop-mobile-tunnel
```

An example ngrok config is included at [deploy/ngrok/ngrok.example.yml](deploy/ngrok/ngrok.example.yml).

Important:

- Gmail cannot display a live password form inside the email itself.
- The reset button opens the password page in the browser.
- `127.0.0.1` links only work on the same device running the app.

## Gunicorn

Run the production server with:

```bash
gunicorn -c gunicorn.conf.py run:app
```

Important env-driven Gunicorn settings:

- `GUNICORN_WORKERS`
- `GUNICORN_THREADS`
- `GUNICORN_TIMEOUT`
- `GUNICORN_MAX_REQUESTS`
- `GUNICORN_MAX_REQUESTS_JITTER`
- `GUNICORN_ACCESSLOG`
- `GUNICORN_ERRORLOG`

Deployment templates are included in [`deploy/`](deploy):

- Nginx reverse proxy config
- systemd service unit
- logrotate policy
- backup script example
- systemd template for scaled instances

## Local Load Balancing

For a local production-style free setup, SmartAttend can run as:

- `Nginx -> Gunicorn cluster -> Flask app`

Start the local cluster:

```bash
flask --app run.py start-local-cluster
```

Check it:

```bash
flask --app run.py local-cluster-status
```

Stop it:

```bash
flask --app run.py stop-local-cluster
```

The local Nginx config at [deploy/nginx/smart_attendance.local.conf](deploy/nginx/smart_attendance.local.conf) uses an upstream with:

- `127.0.0.1:5050`
- `127.0.0.1:5051`

and balances using `least_conn`.

## Production Checklist

1. Copy [.env.example](.env.example) to `.env` and fill in production values.
2. Set `FLASK_ENV=production`.
3. Configure `ALLOWED_HOSTS`, `SECRET_KEY`, `RATELIMIT_STORAGE_URI`, and MySQL credentials.
4. Point private upload folders outside `static/`.
5. Create the college tenant:

```bash
flask --app run.py create-college
```

6. Create the college admin:

```bash
flask --app run.py create-admin
```

7. Run migrations:

```bash
flask --app run.py db upgrade
```

8. Run deployment checks:

```bash
flask --app run.py doctor
```

9. Start Gunicorn:

```bash
gunicorn -c gunicorn.conf.py run:app
```

10. Put the app behind Nginx, Caddy, or another HTTPS reverse proxy.
11. Log in as the college admin and complete `System Setup` inside the app.
12. Monitor logs, database health, backups, and Redis availability.

## How To Use In Production

Recommended rollout order for a real college:

1. Deploy the server stack using the files in [`deploy/`](deploy).
2. Set production environment variables from [.env.example](.env.example).
3. Create the college and admin account.
4. Log in as admin and finish `System Setup`.
5. Add departments, teachers, students, and subjects.
6. Configure ID card template, signatures, and college branding.
7. Publish notices, calendar events, fee structures, and exam setup.
8. Start live usage for attendance, assignments, fees, results, and parent access.

## Status

This project is suitable for academic, internal college, and demo deployment use. For heavier production use, the next steps should focus on broader automated test coverage, deployment monitoring, and infrastructure hardening.
