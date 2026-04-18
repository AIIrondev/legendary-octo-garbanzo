"""
Gunicorn configuration for Inventarsystem.

This configuration ensures that:
1. The BackgroundScheduler runs reliably in only one worker process
2. Appointment status updates and reminders work correctly
3. Multi-worker deployments don't cause race conditions
"""

import os
import sys
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent

# Basic configuration
bind = "unix:/tmp/inventarsystem.sock"
workers = 1  # CRITICAL: Only 1 worker to prevent BackgroundScheduler race conditions
worker_class = "sync"
timeout = 60
graceful_timeout = 20
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = str(PROJECT_ROOT / "logs" / "access.log")
errorlog = str(PROJECT_ROOT / "logs" / "error.log")
log_level = "info"
capture_output = True

# Worker initialization hook to ensure scheduler starts only once
def on_starting(server):
    """Called just before the master process is initialized."""
    print("[GUNICORN] Starting Inventarsystem with scheduler support (1 worker only)")

def when_ready(server):
    """Called just after the server is started."""
    print("[GUNICORN] Server is ready. Scheduler should be active in the single worker process.")

# Ensure the logs directory exists
os.makedirs(PROJECT_ROOT / "logs", exist_ok=True)
