import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError


class Command(BaseCommand):
    help = "Reset an existing account password interactively. Requires trusted server-shell access."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if not user:
            raise CommandError("No matching account.")
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Confirm password: "):
            raise CommandError("Passwords did not match.")
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        user.set_password(password)
        user.save(update_fields=["password"])
        self.stdout.write("Password updated. Existing sessions for this account will be invalidated.")
