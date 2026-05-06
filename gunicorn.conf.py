"""Gunicorn production configuration."""
import multiprocessing
import os
from pathlib import Path


def _int_env(name, default):
    return int(os.environ.get(name, default))

# ── Server socket ─────────────────────────────────────────────────────────────
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5050')
backlog = _int_env('GUNICORN_BACKLOG', 2048)

# ── Workers ───────────────────────────────────────────────────────────────────
# For CPU-bound face-recognition workloads keep workers low; use threads
workers = _int_env('GUNICORN_WORKERS', max(2, multiprocessing.cpu_count()))
threads = _int_env('GUNICORN_THREADS', 2)
worker_class = 'gthread'
worker_connections = _int_env('GUNICORN_WORKER_CONNECTIONS', 1000)
max_requests = _int_env('GUNICORN_MAX_REQUESTS', 1000)
max_requests_jitter = _int_env('GUNICORN_MAX_REQUESTS_JITTER', 100)
preload_app = os.environ.get('GUNICORN_PRELOAD_APP', 'False') == 'True'
_default_tmp_dir = '/dev/shm' if Path('/dev/shm').exists() else '/tmp'
worker_tmp_dir = os.environ.get('GUNICORN_WORKER_TMP_DIR', _default_tmp_dir)

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout = _int_env('GUNICORN_TIMEOUT', 120)          # face-recognition frames can take a moment
graceful_timeout = _int_env('GUNICORN_GRACEFUL_TIMEOUT', 30)
keepalive = _int_env('GUNICORN_KEEPALIVE', 5)

# ── Security ──────────────────────────────────────────────────────────────────
limit_request_line = _int_env('GUNICORN_LIMIT_REQUEST_LINE', 4096)
limit_request_fields = _int_env('GUNICORN_LIMIT_REQUEST_FIELDS', 100)
limit_request_field_size = _int_env('GUNICORN_LIMIT_REQUEST_FIELD_SIZE', 8190)
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = os.environ.get('GUNICORN_ACCESSLOG', '-')
errorlog  = os.environ.get('GUNICORN_ERRORLOG', '-')
loglevel  = os.environ.get('LOG_LEVEL', 'warning').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'
capture_output = os.environ.get('GUNICORN_CAPTURE_OUTPUT', 'True') == 'True'

# ── Process naming ────────────────────────────────────────────────────────────
proc_name = 'smart_attendance'

# ── Reload (dev only) ─────────────────────────────────────────────────────────
reload = os.environ.get('FLASK_ENV') == 'development'
