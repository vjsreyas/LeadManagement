from .models import Business


def sidebar(request):
    if not request.user.is_authenticated:
        return {}
    return {"nav_businesses": Business.objects.all()}
