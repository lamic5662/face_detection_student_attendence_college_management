# SmartAttend System Guide

## Overview

SmartAttend is a multi-college web platform for attendance, academics, communication, and campus operations. It is designed so one platform can serve many colleges while keeping each college's data isolated.

The system supports five user roles:

- `super_admin`
- `admin`
- `teacher`
- `student`
- `parent`

## Core Product Model

SmartAttend uses a multi-college architecture.

- One platform can host many colleges.
- Each college has its own users, notices, settings, timetable, fees, exams, ID cards, and other records.
- `super_admin` manages the whole platform.
- `admin` manages one college only.

## User Roles

### 1. Super Admin

Super admin manages the full platform.

Main responsibilities:

- create colleges
- update college profile, code, and subdomain
- activate or deactivate colleges
- create and manage college admin accounts
- enable or disable features per college
- view college-level usage and onboarding status
- review platform audit logs
- monitor platform activity notifications
- control system-level setup and readiness

### 2. Admin

Admin manages one specific college.

Main responsibilities:

- manage teachers, students, parents, and subjects
- manage departments
- manage notices and academic calendar
- manage fees and payments
- manage timetable and attendance operations
- manage exams and marks
- manage ID card template and approvals
- create user accounts with temporary passwords
- monitor college setup progress

### 3. Teacher

Teacher manages academic delivery and attendance.

Main responsibilities:

- start attendance sessions
- mark attendance
- upload notes, assignments, labs, and academic content
- review assignment submissions
- enter marks and academic records
- manage class-related student interactions

### 4. Student

Student uses the learning and self-service side.

Main responsibilities:

- view attendance
- access notes and assignments
- submit assignments
- view fees, exams, marksheets, notices, and calendar
- request leave
- manage their password after first login
- request or use digital ID card

### 5. Parent

Parent monitors linked student activity.

Main responsibilities:

- view child attendance
- view assignments and results
- view fee information
- view timetable, notices, and calendar
- monitor child-facing academic updates

## Main Features

### Platform and Multi-College Features

- multi-college tenant architecture
- super admin platform control
- college-wise feature enable/disable system
- college detail page with user counts and activity status
- platform audit logs
- platform activity notifications for super admin
- college onboarding and readiness tracking

### Authentication and Security

- role-based login
- super admin login without college code
- college user login with college code
- temporary-password onboarding for new users
- forced password change after first login
- forgot-password email reset flow
- repeated-password prevention
- host allowlist support
- rate limiting
- secure token-based password reset

### Attendance Features

- smart attendance flow
- teacher attendance sessions
- manual attendance operations
- attendance tracking and reporting
- low-attendance checks and alerts

### Academic Features

- departments
- subjects
- timetable
- assignments
- content sharing
- exam setup
- marks entry
- printable marksheet support

### Finance Features

- fee structures
- fee payment records
- receipt generation
- parent fee visibility

### Communication Features

- notice board
- notification bell
- academic calendar
- role-based in-app guidance

### Student Identity Features

- digital ID card request flow
- admin approval flow
- custom ID card template
- front/back card design
- principal signature support
- barcode/QR support

### Operational Features

- file and content previews
- production readiness checks
- tunnel helpers for mobile password reset testing
- local load-balanced cluster helpers

## Feature Access Model

Super admin can control which modules a college is allowed to use.

Examples:

- attendance
- assignments
- exams
- fees
- parent portal
- ID cards
- notice board
- calendar
- timetable
- analytics
- file manager
- live location
- face biometrics

If a feature is disabled for a college:

- it is hidden from navigation
- related dashboard items are hidden
- blocked URLs return `403`

## Security and Account Logic

### Temporary Password Flow

When admin creates student, teacher, or parent accounts:

- admin sets a temporary password
- user signs in with that temporary password
- user is forced to set a private password
- after setting the new password, the user must sign in again

Important security rule:

- admins must not be able to view a user's private password after the user changes it

### Forgot Password Flow

- user opens `Forgot password`
- user enters email
- college users also enter college code unless already college-locked
- the system sends a secure reset link by email
- user resets password in browser
- user signs in again with the new password

## Technology Stack

### Backend

- Python 3.12
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-Login
- Flask-WTF
- Flask-Limiter

### Database and Data

- MySQL
- PyMySQL
- Alembic migrations
- Pandas
- OpenPyXL

### Vision and Smart Attendance

- OpenCV
- `face-recognition`
- `dlib`

### Frontend

- Jinja templates
- Bootstrap 5
- Bootstrap Icons
- custom CSS

### Infrastructure and Runtime

- Gunicorn
- Nginx
- Redis
- systemd deployment templates
- logrotate template
- backup script template

### Optional Mobile/Public Access Tools

- Cloudflare quick tunnel via `cloudflared`
- ngrok

## Production-Style Free Setup

SmartAttend can be run using free software.

Free core setup:

- Flask
- Gunicorn
- Nginx
- MySQL
- Redis
- Cloudflare quick tunnel for testing
- Let's Encrypt for SSL later

Costs may still apply for:

- VPS/server hosting
- domain name
- managed database or managed Redis

## First-Time Setup Guide

This section is for someone setting up SmartAttend for the first time.

### 1. Clone the Project

```bash
git clone <your-repo-url>
cd smart_attendance
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy the sample file:

```bash
cp .env.example .env
```

Update at least:

- `SECRET_KEY`
- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `ALLOWED_HOSTS`
- `RATELIMIT_STORAGE_URI`
- `PUBLIC_BASE_URL`

### 5. Prepare Database

Create the database in MySQL, then run:

```bash
flask --app run.py db upgrade
```

### 6. Create Platform Owner

```bash
flask --app run.py create-super-admin
```

### 7. Create College

```bash
flask --app run.py create-college
```

### 8. Create College Admin

```bash
flask --app run.py create-admin
```

### 9. Start Redis

Example on macOS with Homebrew:

```bash
brew services start redis
redis-cli ping
```

Expected result:

```text
PONG
```

### 10. Run Local Production-Style Stack

Start the local cluster:

```bash
flask --app run.py start-local-cluster
```

Start or reload Nginx.

Local URL:

```text
http://127.0.0.1:8081
```

### 11. Run Health Checks

```bash
flask --app run.py doctor
flask --app run.py local-cluster-status
```

### 12. Log In as Super Admin

Super admin should:

- verify platform setup
- create colleges
- create/manage college admins
- configure feature access per college

### 13. Log In as College Admin

College admin should finish onboarding:

- update college settings
- set address and location
- configure ID card branding
- add departments
- add teachers
- add students
- add parents if needed
- add subjects
- review timetable, notices, fees, exams

## Mobile Reset Link Setup

If the app runs on your laptop and the reset email is opened on a phone, `127.0.0.1` will not work on the phone.

Use a public tunnel for testing.

### Option A: Cloudflare Quick Tunnel

```bash
flask --app run.py start-mobile-tunnel
flask --app run.py mobile-tunnel-status
```

This updates `PUBLIC_BASE_URL` automatically.

### Option B: ngrok

```bash
ngrok http 8081
```

Then set:

```env
PUBLIC_BASE_URL=https://your-ngrok-url.ngrok-free.app
```

Restart the app and send the reset email again.

## Recommended Setup Order for New Colleges

1. create college
2. create college admin
3. super admin sets feature access
4. college admin completes college settings
5. college admin adds academic structure
6. college admin adds users
7. users sign in and replace temporary passwords
8. college starts daily operations

## Useful Commands

```bash
flask --app run.py db upgrade
flask --app run.py doctor
flask --app run.py create-super-admin
flask --app run.py create-college
flask --app run.py create-admin
flask --app run.py start-mobile-tunnel
flask --app run.py mobile-tunnel-status
flask --app run.py stop-mobile-tunnel
flask --app run.py start-local-cluster
flask --app run.py local-cluster-status
flask --app run.py stop-local-cluster
```

## Deployment Notes

Recommended runtime path:

- Browser
- Nginx
- Gunicorn
- Flask app
- MySQL and Redis

For final production:

- use a real domain
- use HTTPS
- use stable hosting
- use Redis as the live shared rate-limit backend
- verify backups and restore process

## Final Summary

SmartAttend is a multi-college college-management platform with:

- five role types
- tenant isolation
- super-admin platform controls
- college-level feature management
- academic, attendance, fee, and identity workflows
- production-style local deployment support

For deployment details, also see [docs/production.md](./production.md).
