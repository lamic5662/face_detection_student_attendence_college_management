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
- enable or disable features per college using 18 configurable modules
- apply tier presets (Starter / Standard / Professional / Enterprise) to a college
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
- manage fees, payments, and fee reminder email configuration
- manage timetable (with conflict detection) and attendance operations
- manage exams, marks, and multi-semester marksheets
- manage ID card template and approvals
- manage batch tracker: monitor student cohort progression and run batch promotions
- configure semester schedules and automated attendance report emails
- use AI assistant to query live college data in natural language
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
- use AI assistant to query attendance, marks, student data, and notes

### 4. Student

Student uses the learning and self-service side.

Main responsibilities:

- view attendance
- access notes and assignments
- submit assignments
- view fees, exams, marksheets (current and previous semesters), notices, and calendar
- request leave
- manage their password after first login
- request or use digital ID card

### 5. Parent

Parent monitors linked student activity.

Main responsibilities:

- view child attendance
- view assignments and results
- view fee information and receive automated fee reminder emails
- view timetable, notices, and calendar
- view official marksheets for any semester
- receive automated weekly attendance report emails when child is below threshold
- monitor child-facing academic updates

## Main Features

### Platform and Multi-College Features

- multi-college tenant architecture
- super admin platform control
- 18-module per-college feature enable/disable system with 4 tier presets
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
- automated weekly attendance report emails to students and parents

### Academic Features

- departments
- subjects
- timetable with slot conflict detection
- semester schedules (official start/end dates per cohort)
- batch tracker with semester progression monitoring and batch promotion
- assignments
- content sharing
- exam setup
- marks entry
- printable marksheets for any semester (not only current)
- student ID auto-generation (COLLEGE-DEPT-YEAR-SEQ format)

### Finance Features

- fee structures
- fee payment records
- receipt generation
- parent fee visibility
- automated fee reminder emails (upcoming / due today / overdue) with configurable schedule

### Communication Features

- notice board
- notification bell
- academic calendar
- role-based in-app guidance

### AI Features

- AI assistant (RAG-based) for admins and teachers
- powered by Groq API (llama-3.3-70b-versatile)
- queries live college data: attendance, students, marks, subjects, notices, notes
- natural-language interface — ask questions, get real answers based on current DB state

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

Super admin controls which of the 18 modules a college can use. If a feature is disabled:

- it is hidden from navigation
- related dashboard items are hidden
- blocked URLs return `403`

### 18 Feature Modules

| Key | Group | Label |
|-----|-------|-------|
| attendance | Academic | Attendance |
| learning_content | Academic | Learning Content |
| exams | Academic | Exams & Marksheets |
| notices | Academic | Notice Board |
| calendar | Academic | Academic Calendar |
| timetable | Academic | Timetable |
| leaves | Academic | Leave Management |
| batch_tracker | Academic | Batch Tracker |
| fees | Operations | Fees |
| fee_reminders | Operations | Fee Reminder Emails |
| parent_portal | Operations | Parent Portal |
| digital_id_cards | Operations | Digital ID Cards |
| analytics | Operations | Analytics |
| file_manager | Operations | File Manager |
| report_emails | Operations | Automated Report Emails |
| face_biometrics | Advanced | Face Biometrics |
| live_location | Advanced | Live Location |
| ai_assistant | Advanced | AI Assistant |

### Tier Presets

| Tier | Modules | Best for |
|------|---------|----------|
| Starter | 4 | New or small college |
| Standard | 10 | Most colleges |
| Professional | 15 | Established college |
| Enterprise | 18 | All features enabled |

## Automated Emails

### Weekly Attendance Report Emails

Configured per college under **Sidebar → Semester Schedules → Report Schedule**.

- toggle enabled/disabled
- set send day (Mon–Sun) and hour
- filter by department, semester, or admission year (leave blank = all students)
- click **Send Now** to trigger a manual send immediately

Student email: subject-wise table showing this week and overall attendance %, with a warning block for any subject below the threshold.

Parent email: triggered only when at least one subject is below the low-attendance threshold (default 75%).

### Fee Reminder Emails

Configured per college under **Sidebar → Fees → Fee Reminder Emails** card.

- toggle enabled/disabled
- set how many days before due date to start reminding (1–30 days)
- choose whether to send on the due date itself
- choose whether to send overdue reminders
- set the send hour (0–23)

One consolidated email per student covers all qualifying fees in a single table — no per-fee separate emails.

Parent copy is sent automatically to each linked parent.

## Batch Tracker

Tracks cohort (admission year) progression through semesters.

- expected semester is calculated from admission year and current date
- if semester schedules are configured, the official start/end dates are used instead
- status badges: on-track / behind / far-behind
- Batch Overview page shows per-cohort cards with progress bars
- Promote button bumps all on-track students to the next semester

Access via **Sidebar → Batch Overview**.

## AI Assistant

Available to admins and teachers when the `ai_assistant` feature is enabled.

- access via **Sidebar → AI Assistant**
- ask in plain English: "Which students have below 75% attendance?", "List recent notices", "How many students are in BCA semester 3?"
- the system detects intent, fetches real DB data, and answers using the Groq AI model
- responses are based on live data — not guesses

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
- APScheduler (BackgroundScheduler, Asia/Kathmandu timezone)

### AI

- Groq API — llama-3.3-70b-versatile
- RAG pattern: context built from live DB data and injected as system prompt

### Database and Data

- MySQL (30+ tables)
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
- `GROQ_API_KEY` (required for AI assistant feature)

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
- configure feature access per college (apply a tier preset or enable individual modules)

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
- configure semester schedules (optional but recommended for batch tracker accuracy)
- configure report email schedule (optional)
- configure fee reminder emails (optional)
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
3. super admin sets feature access (apply tier preset)
4. college admin completes college settings
5. college admin adds academic structure
6. college admin adds users
7. users sign in and replace temporary passwords
8. college starts daily operations
9. configure semester schedules for batch tracker accuracy
10. configure report email and fee reminder schedules

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
- set `GROQ_API_KEY` for AI assistant
- verify backups and restore process

## Final Summary

SmartAttend is a multi-college college-management platform with:

- five role types
- tenant isolation
- super-admin platform controls with 18 feature modules and 4 tier presets
- college-level feature management
- academic, attendance, fee, and identity workflows
- automated email services (attendance reports + fee reminders)
- AI assistant powered by RAG + Groq API
- batch tracker for cohort progression monitoring
- timetable conflict detection
- multi-semester marksheet history
- production-style local deployment support

For deployment details, also see [docs/production.md](./production.md).
