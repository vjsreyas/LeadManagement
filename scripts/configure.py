import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent.parent
destination = root / ".env"
if destination.exists():
    raise SystemExit(".env already exists; left it unchanged.")
text = (root / ".env.example").read_text()
for placeholder, value in {
    "replace-with-a-random-secret": secrets.token_urlsafe(48),
    "replace-with-a-random-setup-token": secrets.token_urlsafe(32),
}.items():
    text = text.replace(placeholder, value)
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write(text)
print("Created private .env. Set DATABASE_URL to your Supabase session-pooler URL.")
print("Use SETUP_TOKEN from that file on the first-run setup page. Keep this file private.")
