# SmartAttend

SmartAttend is a Flask-based college management and smart attendance system built for multi-role campus operations. It combines face-recognition attendance with student, teacher, parent, and admin workflows in one application.

## Main Features

- Face-based attendance with liveness/blink verification
- Multi-role login for admin, teacher, student, and parent
- Attendance sessions, live marking, manual overrides, and downloadable reports
- Student face enrollment and profile management
- Teacher content publishing for notes, assignments, labs, and question sets
- In-app preview for notes and supported attachments
- Leave request workflow
- Exam scheduling, marks entry, and printable marksheets
- Fee structures and payment tracking
- Parent dashboard with attendance, fees, results, timetable, and location tracking
- Student digital ID card request flow and admin approval
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
flask --app run.py create-admin
flask --app run.py check-classes
```

`check-classes` sends alerts when a scheduled class has passed and no attendance session was started.

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

## Production Notes

- Configure a strong `SECRET_KEY`
- Use a shared limiter backend such as Redis via `RATELIMIT_STORAGE_URI`
- Keep `CONTENT_UPLOAD_FOLDER` outside the public `static` directory
- Do not commit `.env`, runtime logs, or generated uploads
- Consider moving the large dlib model file to Git LFS

## Status

This project is suitable for academic, internal college, and demo deployment use. For heavier production use, the next steps should focus on broader automated test coverage, deployment monitoring, and infrastructure hardening.
