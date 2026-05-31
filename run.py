import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from app import create_app
from extensions import db
from utils.system_setup import evaluate_production_setup
from utils.time import utc_now_naive

# Import all models so Flask-Migrate can detect them
from models import (  # noqa: F401
    College, User, Department, Student, Teacher, Subject,
    AttendanceSession, AttendanceRecord, LeaveRequest,
    Notice, TimetableSlot, Exam, Mark, FeeStructure, FeePayment,
)
from models.parent import ParentStudent, TeacherStatus, ClassAlert  # noqa: F401
from models.location import StudentLocation  # noqa: F401
from models.setting import CollegeSetting   # noqa: F401
from models.academic_calendar import AcademicCalendarEvent  # noqa: F401

app = create_app()

_TRYCLOUDFLARE_RE = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com', re.IGNORECASE)


def _env_path() -> Path:
    return Path(app.root_path) / '.env'


def _tunnel_state_dir() -> Path:
    path = Path(app.instance_path) / 'tunnel'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tunnel_pid_path() -> Path:
    return _tunnel_state_dir() / 'cloudflared.pid'


def _tunnel_url_path() -> Path:
    return _tunnel_state_dir() / 'cloudflared.url'


def _tunnel_log_path() -> Path:
    return _tunnel_state_dir() / 'cloudflared.log'


def _extract_trycloudflare_url(text: str) -> str | None:
    match = _TRYCLOUDFLARE_RE.search(text or '')
    return match.group(0) if match else None


def _is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _stored_tunnel_pid() -> int | None:
    path = _tunnel_pid_path()
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding='utf-8').strip())
    except (TypeError, ValueError):
        return None


def _stored_tunnel_url() -> str:
    path = _tunnel_url_path()
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8').strip()


def _write_public_base_url(url: str) -> None:
    env_path = _env_path()
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding='utf-8').splitlines()

    replaced = False
    updated = []
    for line in lines:
        if line.startswith('PUBLIC_BASE_URL='):
            updated.append(f'PUBLIC_BASE_URL={url}')
            replaced = True
        else:
            updated.append(line)

    if not replaced:
        updated.append(f'PUBLIC_BASE_URL={url}')

    env_path.write_text('\n'.join(updated) + '\n', encoding='utf-8')


def _stop_tunnel_process(pid: int) -> bool:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
    return True


def _clear_tunnel_state() -> None:
    for path in (_tunnel_pid_path(), _tunnel_url_path()):
        if path.exists():
            path.unlink()


def _cluster_state_dir() -> Path:
    path = Path(app.instance_path) / 'cluster'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cluster_ports() -> list[int]:
    raw = (os.environ.get('LOCAL_CLUSTER_PORTS') or '5050,5051').strip()
    ports = []
    for item in raw.split(','):
        item = item.strip()
        if item:
            ports.append(int(item))
    return ports or [5050, 5051]


def _cluster_pid_path(port: int) -> Path:
    return _cluster_state_dir() / f'gunicorn-{port}.pid'


def _cluster_log_path(port: int) -> Path:
    return _cluster_state_dir() / f'gunicorn-{port}.log'


def _stored_cluster_pid(port: int) -> int | None:
    path = _cluster_pid_path(port)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding='utf-8').strip())
    except (TypeError, ValueError):
        return None


def _cluster_workers() -> int:
    return int(os.environ.get('LOCAL_CLUSTER_WORKERS', 2))


def _cluster_threads() -> int:
    return int(os.environ.get('LOCAL_CLUSTER_THREADS', 2))


def _start_cluster_instance(port: int) -> tuple[int, Path]:
    gunicorn = shutil.which('gunicorn')
    if not gunicorn:
        raise RuntimeError('gunicorn is not installed in the current Python environment.')

    log_path = _cluster_log_path(port)
    env = os.environ.copy()
    env['FLASK_ENV'] = 'production'
    env['ALLOW_INSECURE_LOCAL_HTTP'] = 'True'
    env['SESSION_COOKIE_SECURE'] = 'False'
    env['REMEMBER_COOKIE_SECURE'] = 'False'
    env['GUNICORN_BIND'] = f'127.0.0.1:{port}'
    env['GUNICORN_WORKERS'] = str(_cluster_workers())
    env['GUNICORN_THREADS'] = str(_cluster_threads())
    env['GUNICORN_RELOAD'] = 'False'

    with open(log_path, 'w', encoding='utf-8') as log_handle:
        proc = subprocess.Popen(
            [gunicorn, '-c', 'gunicorn.conf.py', 'run:app'],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
            cwd=app.root_path,
        )

    _cluster_pid_path(port).write_text(str(proc.pid), encoding='utf-8')
    return proc.pid, log_path


def _stop_cluster_instance(port: int) -> bool:
    pid = _stored_cluster_pid(port)
    if not pid:
        return False
    stopped = _stop_tunnel_process(pid)
    path = _cluster_pid_path(port)
    if path.exists():
        path.unlink()
    return stopped


def _mobile_tunnel_target() -> str:
    explicit = (os.environ.get('MOBILE_TUNNEL_TARGET') or '').strip()
    if explicit:
        return explicit

    nginx_local_conf = Path('/opt/homebrew/etc/nginx/servers/smart_attendance.conf')
    if nginx_local_conf.exists():
        return 'http://127.0.0.1:8081'

    port = int(os.environ.get('PORT', 5050))
    return f'http://127.0.0.1:{port}'


@app.cli.command('init-db')
def init_db():
    """Create all tables and seed a default college with departments."""
    with app.app_context():
        db.create_all()
        print('Tables created.')

        college = College.ensure_default()
        print(f'Using college: {college.name} [{college.code}]')

        depts = [
            ('Bachelor of Computer Applications', 'BCA'),
            ('Bachelor of Information Technology', 'BIT'),
            ('Bachelor of Science CSIT', 'BSc.CSIT'),
            ('Bachelor of Business Administration', 'BBA'),
            ('Bachelor of Engineering', 'BE'),
        ]
        for name, code in depts:
            if not Department.query.filter_by(college_id=college.id, code=code).first():
                db.session.add(Department(college_id=college.id, name=name, code=code))

        db.session.commit()
        print('Default departments seeded.')
        if not User.query.filter_by(college_id=college.id, role='admin').first():
            print('No admin account exists yet. Run: flask create-admin')
        else:
            print('Admin account already exists.')


@app.cli.command('create-college')
def create_college():
    """Create a new college tenant."""
    with app.app_context():
        name = input('College name: ').strip()
        code = input('College code: ').strip().upper()
        subdomain = input('Subdomain (optional): ').strip().lower() or None

        if not name or not code:
            print('College name and code are required.')
            return
        if College.query.filter_by(code=code).first():
            print(f'College code {code} already exists.')
            return
        if subdomain and College.query.filter_by(subdomain=subdomain).first():
            print(f'Subdomain {subdomain} already exists.')
            return

        college = College(name=name, code=code, subdomain=subdomain)
        db.session.add(college)
        db.session.flush()
        db.session.add(CollegeSetting(college_id=college.id, college_name=name))
        db.session.commit()
        print(f'College {name} [{code}] created.')


@app.cli.command('create-admin')
def create_admin():
    """Interactively create a new admin user."""
    with app.app_context():
        colleges = College.query.filter_by(is_active=True).order_by(College.name).all()
        if not colleges:
            print('No active college exists. Run: flask create-college')
            return

        if len(colleges) == 1:
            college = colleges[0]
        else:
            print('Available colleges:')
            for college_option in colleges:
                print(f'  - {college_option.code}: {college_option.name}')
            college_code = input('College code: ').strip().upper()
            college = College.query.filter_by(code=college_code, is_active=True).first()
            if college is None:
                print(f'College {college_code} not found.')
                return

        email = input('Admin email: ').strip().lower()
        name  = input('Full name: ').strip()
        pw    = input('Password: ').strip()
        if User.query.filter_by(college_id=college.id, email=email).first():
            print(f'User {email} already exists in {college.code}.')
            return
        u = User(college_id=college.id, name=name, email=email, role='admin', is_active=True)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        print(f'Admin {email} created for {college.name}.')


@app.cli.command('create-super-admin')
def create_super_admin():
    """Create a platform super admin user."""
    with app.app_context():
        college = College.ensure_default()
        email = input('Super admin email: ').strip().lower()
        name = input('Full name: ').strip()
        pw = input('Password: ').strip()
        if User.query.filter_by(college_id=college.id, email=email).first():
            print(f'User {email} already exists in {college.code}.')
            return
        u = User(college_id=college.id, name=name, email=email, role='super_admin', is_active=True)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        print(f'Super admin {email} created.')


@app.cli.command('check-classes')
def check_classes():
    """Notify students/parents about classes that haven't started 15+ min past scheduled time."""
    from datetime import datetime, date, time as dtime
    from models.timetable import TimetableSlot
    from models.attendance import AttendanceSession
    from models.parent import ParentStudent, ClassAlert
    from services.notification_service import send_absent_teacher_alert

    with app.app_context():
        now = datetime.now()
        today = date.today()
        today_dow = today.weekday()
        cutoff = now.replace(second=0, microsecond=0)

        slots = TimetableSlot.query.filter_by(
            day_of_week=today_dow, slot_type='class'
        ).all()

        total_sent = 0
        for slot in slots:
            if not slot.subject:
                continue

            # Check if slot ended 15+ min ago with no session started
            slot_end = datetime.combine(today, slot.end_time)
            if (cutoff - slot_end).total_seconds() < 15 * 60:
                continue

            # Skip if a session was started
            session = AttendanceSession.query.filter(
                AttendanceSession.subject_id == slot.subject_id,
                AttendanceSession.date == today,
                AttendanceSession.status.in_(['active', 'completed'])
            ).first()
            if session:
                continue

            # Prevent duplicate alert for same slot today
            existing = ClassAlert.query.filter_by(
                slot_id=slot.id, alert_date=today
            ).first()
            if existing:
                continue

            # Collect student + parent emails
            from models.student import Student
            students = Student.query.filter_by(
                department_id=slot.department_id,
                semester=slot.semester
            ).all()

            recipients = []
            for s in students:
                if s.user.email:
                    recipients.append(s.user.email)
                for link in ParentStudent.query.filter_by(student_id=s.id).all():
                    parent_user = db.session.get(User, link.parent_id)
                    if parent_user and parent_user.email:
                        recipients.append(parent_user.email)

            recipients = list(set(recipients))
            teacher = slot.subject.teacher
            teacher_name = teacher.user.name if teacher else 'Unknown'
            slot_time = f"{slot.start_time.strftime('%H:%M')} – {slot.end_time.strftime('%H:%M')}"
            dept_name = slot.department.name if slot.department else 'N/A'

            sent = send_absent_teacher_alert(
                recipients=recipients,
                subject_name=slot.subject.name,
                teacher_name=teacher_name,
                slot_time=slot_time,
                department=dept_name,
                semester=slot.semester or 0,
            )

            alert = ClassAlert(
                college_id=slot.department.college_id,
                slot_id=slot.id,
                alert_date=today,
                recipient_count=sent,
                triggered_by='auto',
            )
            db.session.add(alert)
            db.session.commit()
            total_sent += sent
            print(f'  Alert sent: {slot.subject.name} @ {slot_time} — {sent} recipients')

        print(f'check-classes done. Total notifications sent: {total_sent}')


@app.cli.command('doctor')
def doctor():
    """Run deployment-readiness checks."""
    with app.app_context():
        report = evaluate_production_setup(app)

    print('Production doctor report')
    print('------------------------')
    if report['failures']:
        print('FAIL')
        for item in report['checks']:
            if item['status'] == 'fail':
                print(f"  - {item['label']}: {item['detail']}")
    else:
        print('PASS')

    if report['warnings']:
        print('Warnings')
        for item in report['checks']:
            if item['status'] == 'warning':
                print(f"  - {item['label']}: {item['detail']}")

    if report['failures']:
        raise SystemExit(1)


@app.cli.command('start-local-cluster')
def start_local_cluster():
    """Start multiple local Gunicorn instances for Nginx load balancing."""
    ports = _cluster_ports()
    started = []

    for port in ports:
        pid = _stored_cluster_pid(port)
        if pid and _is_pid_running(pid):
            started.append((port, pid, _cluster_log_path(port), True))
            continue

        pid, log_path = _start_cluster_instance(port)
        time.sleep(0.8)
        if not _is_pid_running(pid):
            tail = log_path.read_text(encoding='utf-8', errors='ignore')[-4000:]
            raise RuntimeError(
                f'Gunicorn instance on port {port} failed to start.\n'
                f'--- log: {log_path} ---\n{tail}'
            )
        started.append((port, pid, log_path, False))

    print('Local Gunicorn cluster')
    print('----------------------')
    print(f'Workers per instance: {_cluster_workers()}')
    print(f'Threads per instance: {_cluster_threads()}')
    for port, pid, log_path, reused in started:
        label = 'reused' if reused else 'started'
        print(f'  - {label}: 127.0.0.1:{port} (pid {pid}) log={log_path}')
    print('Nginx can now load balance across these local instances.')


@app.cli.command('local-cluster-status')
def local_cluster_status():
    """Show the local Gunicorn cluster state."""
    ports = _cluster_ports()
    print('Local Gunicorn cluster status')
    print('-----------------------------')
    print(f'Configured ports: {", ".join(str(p) for p in ports)}')
    print(f'Workers per instance: {_cluster_workers()}')
    print(f'Threads per instance: {_cluster_threads()}')
    for port in ports:
        pid = _stored_cluster_pid(port)
        running = bool(pid and _is_pid_running(pid))
        print(
            f'  - 127.0.0.1:{port} | pid={pid or "(none)"} '
            f'| running={"yes" if running else "no"} | log={_cluster_log_path(port)}'
        )


@app.cli.command('stop-local-cluster')
def stop_local_cluster():
    """Stop the local Gunicorn cluster instances."""
    ports = _cluster_ports()
    print('Stopping local Gunicorn cluster')
    print('-------------------------------')
    for port in ports:
        stopped = _stop_cluster_instance(port)
        print(f'  - 127.0.0.1:{port}: {"stopped" if stopped else "not running"}')


@app.cli.command('start-mobile-tunnel')
def start_mobile_tunnel():
    """Start a quick Cloudflare tunnel, store the public URL, and update PUBLIC_BASE_URL."""
    cloudflared = shutil.which('cloudflared')
    if not cloudflared:
        print('cloudflared is not installed. Run: brew install cloudflared')
        raise SystemExit(1)

    existing_pid = _stored_tunnel_pid()
    existing_url = _stored_tunnel_url()
    if existing_pid and _is_pid_running(existing_pid) and existing_url:
        _write_public_base_url(existing_url)
        print('Existing mobile tunnel is already running.')
        print(f'PID: {existing_pid}')
        print(f'URL: {existing_url}')
        print('PUBLIC_BASE_URL refreshed in .env')
        return

    _clear_tunnel_state()
    log_path = _tunnel_log_path()
    target = _mobile_tunnel_target()

    with open(log_path, 'w', encoding='utf-8') as log_handle:
        proc = subprocess.Popen(
            [cloudflared, 'tunnel', '--url', target],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    url = ''
    deadline = time.time() + 25
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        log_text = log_path.read_text(encoding='utf-8', errors='ignore')
        url = _extract_trycloudflare_url(log_text) or ''
        if url:
            break
        time.sleep(0.5)

    if not url:
        if proc.poll() is None:
            _stop_tunnel_process(proc.pid)
        print('Failed to create a mobile tunnel. Review the log below:')
        print('--- cloudflared.log ---')
        print(log_path.read_text(encoding='utf-8', errors='ignore')[-4000:])
        raise SystemExit(1)

    _tunnel_pid_path().write_text(str(proc.pid), encoding='utf-8')
    _tunnel_url_path().write_text(url, encoding='utf-8')
    _write_public_base_url(url)

    print('Mobile tunnel started.')
    print(f'PID: {proc.pid}')
    print(f'Local target: {target}')
    print(f'Public URL: {url}')
    print('PUBLIC_BASE_URL updated in .env')
    print('Restart SmartAttend and send the password reset email again.')


@app.cli.command('mobile-tunnel-status')
def mobile_tunnel_status():
    """Show the current Cloudflare mobile tunnel state."""
    pid = _stored_tunnel_pid()
    url = _stored_tunnel_url()
    running = bool(pid and _is_pid_running(pid))

    print('Mobile Tunnel Status')
    print('--------------------')
    print(f'PID: {pid or "(none)"}')
    print(f'Running: {"yes" if running else "no"}')
    print(f'Local target: {_mobile_tunnel_target()}')
    print(f'URL: {url or "(none)"}')
    print(f'PUBLIC_BASE_URL: {app.config.get("PUBLIC_BASE_URL") or "(not set)"}')
    print(f'Log: {_tunnel_log_path()}')


@app.cli.command('stop-mobile-tunnel')
def stop_mobile_tunnel():
    """Stop the stored Cloudflare mobile tunnel process."""
    pid = _stored_tunnel_pid()
    if not pid:
        print('No managed mobile tunnel PID is stored.')
        return

    stopped = _stop_tunnel_process(pid)
    _clear_tunnel_state()
    if stopped:
        print(f'Stopped mobile tunnel PID {pid}.')
    else:
        print(f'Mobile tunnel PID {pid} was not running.')


@app.cli.command('tunnel-guide')
def tunnel_guide():
    """Print the ngrok/mobile testing steps for password reset links."""
    port = int(os.environ.get('PORT', 5050))
    target = _mobile_tunnel_target()
    current_public_base = app.config.get('PUBLIC_BASE_URL') or ''

    print('Mobile Password Reset Tunnel Guide')
    print('----------------------------------')
    print(f'Local app port: {port}')
    print(f'Managed tunnel target: {target}')
    print(f'Current PUBLIC_BASE_URL: {current_public_base or "(not set)"}')
    print()
    print('1. Start the local app if it is not running:')
    print(f'   python run.py  # serves on http://127.0.0.1:{port}')
    print()
    print('2. The easiest way now is:')
    print('   flask --app run.py start-mobile-tunnel')
    print()
    print('3. Or manually start ngrok in another terminal:')
    print(f'   ngrok http {port}')
    print()
    print('   Or use the included config:')
    print('   ngrok start smartattend --config deploy/ngrok/ngrok.example.yml')
    print()
    print('4. Copy the HTTPS forwarding URL and set it as PUBLIC_BASE_URL in .env')
    print()
    print('5. Restart the SmartAttend app after changing .env')
    print()
    print('6. Send the forgot-password email again and open it on your phone.')
    print()
    print('Important:')
    print('- Email apps cannot show the password form directly inside Gmail.')
    print('- The reset button always opens the password page in a browser.')
    print('- 127.0.0.1 links only work on the same device running the app.')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)
