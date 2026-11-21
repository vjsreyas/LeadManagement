import os
from pathlib import Path
import shutil
import subprocess
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse

database_url = os.getenv("DATABASE_URL", "")
if not database_url or not shutil.which("pg_dump"):
    raise SystemExit("Set DATABASE_URL securely and install a compatible PostgreSQL pg_dump client first.")
parsed = urlparse(database_url)
if parsed.scheme not in ("postgres", "postgresql"):
    raise SystemExit("DATABASE_URL must be a PostgreSQL URI.")
output_dir = Path(__file__).resolve().parent.parent / "backups"
output_dir.mkdir(mode=0o700, exist_ok=True)
output = output_dir / ("infinitus-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".dump")
env = {**os.environ, "PGPASSWORD": unquote(parsed.password or ""),
       "PGSSLMODE": parse_qs(parsed.query).get("sslmode", ["require"])[0]}
fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
try:
    with os.fdopen(fd, "wb") as file:
        result = subprocess.run(["pg_dump", "--host", parsed.hostname or "localhost", "--port", str(parsed.port or 5432),
            "--username", unquote(parsed.username or ""), "--dbname", unquote(parsed.path.lstrip("/")),
            "--schema", "infinitus", "--format", "custom", "--no-owner", "--no-acl", "--no-password"],
            env=env, stdout=file, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        output.unlink(missing_ok=True)
        raise SystemExit("Backup failed. Check database reachability, credentials, schema permissions and pg_dump version. No partial dump retained.")
except BaseException:
    output.unlink(missing_ok=True)
    raise
print(f"Private app schema backup saved to {output}")
