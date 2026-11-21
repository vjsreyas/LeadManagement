from django.contrib.auth import get_user_model
from django.shortcuts import redirect


class SetupMiddleware:
    """Send everyone to first-run setup until the owner account exists."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        exempt = request.path in ("/health/", "/setup/") or request.path.startswith("/static/")
        if not exempt and not get_user_model().objects.exists():
            return redirect("setup")
        return self.get_response(request)
