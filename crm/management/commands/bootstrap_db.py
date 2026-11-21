from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create the private app schema before migrations (Supabase / PostgreSQL)."

    def handle(self, *args, **options):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("CREATE SCHEMA IF NOT EXISTS infinitus")
                cursor.execute("REVOKE ALL ON SCHEMA infinitus FROM PUBLIC")
                for role in ("anon", "authenticated"):
                    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
                    if cursor.fetchone():
                        cursor.execute(f'REVOKE ALL ON SCHEMA infinitus FROM "{role}"')
            self.stdout.write("Private infinitus schema ready.")
