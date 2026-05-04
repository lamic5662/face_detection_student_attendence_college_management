"""Gunicorn production configuration."""
import multiprocessing
import os

# ── Server socket ─────────────────────────────────────────────────────────────
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5050')
backlog = 2048

# ── Workers ───────────────────────────────────────────────────────────────────
# For CPU-bound face-recognition workloads keep workers low; use threads
workers = int(os.environ.get('GUNICORN_WORKERS', max(2, multiprocessing.cpu_count())))
threads = int(os.environ.get('GUNICORN_THREADS', 2))
worker_class = 'gthread'
worker_connections = 1000

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout = 120          # face-recognition frames can take a moment
graceful_timeout = 30
keepalive = 5

# ── Security ──────────────────────────────────────────────────────────────────
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = 'logs/access.log'
errorlog  = 'logs/gunicorn_error.log'
loglevel  = os.environ.get('LOG_LEVEL', 'warning').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# ── Process naming ────────────────────────────────────────────────────────────
proc_name = 'smart_attendance'

# ── Reload (dev only) ─────────────────────────────────────────────────────────
reload = os.environ.get('FLASK_ENV') == 'development'
