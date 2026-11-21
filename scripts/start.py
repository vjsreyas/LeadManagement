import os
from pathlib import Path
import signal
import subprocess
import sys
import time

os.chdir(Path(__file__).resolve().parent.parent)
for command in ("bootstrap_db", "migrate"):
    subprocess.run([sys.executable, "manage.py", command, "--noinput"] if command == "migrate" else [sys.executable, "manage.py", command], check=True)

children = []
stopping = False


def stop(*args):
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
children.append(subprocess.Popen(["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:" + os.getenv("PORT", "8000"),
    "--workers", "1", "--threads", "4", "--timeout", "60", "--max-requests", "1000", "--max-requests-jitter", "100",
    "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-", "--error-logfile", "-",
    "--access-logformat", '%(h)s %(m)s %(U)s %(s)s %(L)s']))
exit_code = 0
try:
    while not stopping:
        for child in children:
            if child.poll() is not None:
                exit_code = child.returncode or 1
                stopping = True
        time.sleep(.5)
finally:
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
sys.exit(exit_code)
