import csv
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, connection as db_connection, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import BusinessForm, LeadForm, PartnerForm, SetupForm
from .models import Business, Lead, LeadNote, LoginAttempt

User = get_user_model()
MAX_USERS = 2


def health(request):
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)


# --- sign in / setup -------------------------------------------------------

def _key(request, identity):
    return hashlib.sha256((identity.casefold().strip() + ":" + request.META.get("REMOTE_ADDR", "")).encode()).hexdigest()


def _throttled(request, identity):
    attempt, _ = LoginAttempt.objects.get_or_create(key=_key(request, identity))
    return attempt.failures >= 8 and attempt.last_attempt > timezone.now() - timedelta(minutes=15)


def _failed(request, identity):
    attempt, _ = LoginAttempt.objects.get_or_create(key=_key(request, identity))
    recent = attempt.last_attempt > timezone.now() - timedelta(minutes=15)
    attempt.failures = attempt.failures + 1 if recent else 1
    attempt.last_attempt = timezone.now()
    attempt.save()


def setup(request):
    if User.objects.exists():
        return redirect("dashboard")
    form = SetupForm(request.POST or None)
    if request.method == "POST":
        if _throttled(request, "setup"):
            form.add_error(None, "Too many attempts. Please wait 15 minutes.")
        elif not settings.DEBUG and (not settings.SETUP_TOKEN or not secrets.compare_digest(request.POST.get("setup_token", ""), settings.SETUP_TOKEN)):
            _failed(request, "setup")
            form.add_error("setup_token", "That setup token does not match the SETUP_TOKEN environment variable.")
        elif form.is_valid():
            try:
                with transaction.atomic():
                    if User.objects.exists():
                        raise IntegrityError
                    user = form.save(commit=False)
                    user.is_staff = True
                    user.save()
                    for i, (name, color) in enumerate([("Gyms", "#2f7d6b"), ("Real estate", "#3b6fd4"), ("Clinics", "#8a4fbf")]):
                        Business.objects.get_or_create(name=name, defaults={"color": color, "position": i})
                login(request, user)
                messages.success(request, "All set. Add your partner under Team & account.")
                return redirect("dashboard")
            except IntegrityError:
                form.add_error(None, "Setup is already complete. Reload and sign in.")
    return render(request, "registration/setup.html", {"form": form, "page_title": "Set up"})


def signin(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        identity = request.POST.get("username", "")
        if _throttled(request, identity):
            form.add_error(None, "Too many sign-in attempts. Please wait 15 minutes.")
        elif form.is_valid():
            LoginAttempt.objects.filter(key=_key(request, identity)).delete()
            login(request, form.get_user())
            return redirect("dashboard")
        else:
            _failed(request, identity)
    return render(request, "registration/login.html", {"form": form, "page_title": "Sign in"})


# --- dashboard -------------------------------------------------------------

@login_required
def dashboard(request):
    today = timezone.localdate()
    leads = Lead.objects.all()
    counts = {row["status"]: row["n"] for row in leads.values("status").annotate(n=Count("pk"))}
    statuses = [{"key": k, "label": label, "count": counts.get(k, 0)} for k, label in Lead.Status.choices]
    open_leads = leads.filter(status__in=Lead.OPEN)
    won, lost = counts.get("won", 0), counts.get("lost", 0)

    per_business = []
    for business in Business.objects.all():
        rows = {r["status"]: r["n"] for r in leads.filter(business=business).values("status").annotate(n=Count("pk"))}
        per_business.append({
            "business": business, "total": sum(rows.values()),
            "open": sum(rows.get(s, 0) for s in Lead.OPEN),
            "chips": [{"key": k, "label": label, "count": rows.get(k, 0)} for k, label in Lead.Status.choices if rows.get(k)],
            "won": rows.get("won", 0),
        })

    follow_ups = open_leads.filter(next_follow_up__lte=today + timedelta(days=2)).select_related("business", "owner").order_by("next_follow_up")[:10]
    return render(request, "crm/dashboard.html", {
        "page_title": "Dashboard", "nav": "dashboard", "statuses": statuses, "per_business": per_business,
        "total": leads.count(), "open_count": open_leads.count(), "won": won,
        "win_rate": round(won / (won + lost) * 100) if won + lost else None,
        "won_value": leads.filter(status="won").aggregate(n=Sum("value"))["n"] or 0,
        "pipeline_value": open_leads.aggregate(n=Sum("value"))["n"] or 0,
        "follow_ups": follow_ups, "today": today,
        "overdue_count": open_leads.filter(next_follow_up__lt=today).count(),
        "trials": leads.filter(status="trial").select_related("business", "owner").order_by("trial_end")[:8],
        "bookings": leads.filter(status="booked").select_related("business", "owner").order_by("booked_for")[:8],
        "recent": leads.select_related("business", "owner")[:6],
    })


# --- leads -----------------------------------------------------------------

def _filtered(request, business=None):
    leads = Lead.objects.select_related("business", "owner")
    if business:
        leads = leads.filter(business=business)
    elif request.GET.get("business", "").isdigit():
        leads = leads.filter(business_id=request.GET["business"])
    status = request.GET.get("status", "")
    if status == "open":
        leads = leads.filter(status__in=Lead.OPEN)
    elif status in Lead.Status.values:
        leads = leads.filter(status=status)
    if request.GET.get("owner", "").isdigit():
        leads = leads.filter(owner_id=request.GET["owner"])
    if request.GET.get("due") == "1":
        leads = leads.filter(status__in=Lead.OPEN, next_follow_up__lte=timezone.localdate())
    q = request.GET.get("q", "").strip()
    if q:
        leads = leads.filter(Q(name__icontains=q) | Q(contact_name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q)
                             | Q(location__icontains=q) | Q(notes__icontains=q))
    return leads


@login_required
def lead_list(request, slug=None):
    business = get_object_or_404(Business, slug=slug) if slug else None
    leads = _filtered(request, business)
    scope = Lead.objects.filter(business=business) if business else Lead.objects.all()
    counts = {r["status"]: r["n"] for r in scope.values("status").annotate(n=Count("pk"))}
    tabs = [{"key": "", "label": "All", "count": sum(counts.values())},
            {"key": "open", "label": "Open", "count": sum(counts.get(s, 0) for s in Lead.OPEN)}]
    tabs += [{"key": k, "label": label, "count": counts.get(k, 0)} for k, label in Lead.Status.choices]
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "crm/leads.html", {
        "page_title": business.name if business else "All leads", "nav": "" if business else "leads", "active_business": business.pk if business else None,
        "business": business, "leads": Paginator(leads, 40).get_page(request.GET.get("page")), "total": leads.count(),
        "tabs": tabs, "active_tab": request.GET.get("status", ""), "statuses": Lead.Status.choices,
        "partners": User.objects.filter(is_active=True), "businesses": Business.objects.all(),
        "querystring": query.urlencode(), "today": timezone.localdate(),
    })


@login_required
def lead_detail(request, pk):
    lead = get_object_or_404(Lead.objects.select_related("business", "owner"), pk=pk)
    return render(request, "crm/lead_detail.html", {
        "page_title": lead.name, "nav": "", "active_business": lead.business_id, "lead": lead,
        "timeline": lead.timeline.select_related("author"), "statuses": Lead.Status.choices, "today": timezone.localdate()})


def _log(lead, user, text, is_status=False):
    LeadNote.objects.create(lead=lead, author=user, body=text, is_status=is_status)


@login_required
def lead_edit(request, pk=None):
    lead = get_object_or_404(Lead, pk=pk) if pk else Lead(owner=request.user)
    if not pk:
        if request.GET.get("business", "").isdigit():
            lead.business_id = int(request.GET["business"])
        if not Business.objects.exists():
            messages.info(request, "Add a business first, such as Gyms or Real estate.")
            return redirect("businesses")
    old_status = lead.status
    form = LeadForm(request.POST or None, instance=lead)
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        if not lead.owner_id:
            lead.owner = request.user
        if lead.status != old_status or not pk:
            lead.closed_at = timezone.now() if lead.status in ("won", "lost") else None
        lead.save()
        if not pk:
            _log(lead, request.user, f"Added to {lead.business} as {lead.get_status_display()}", True)
        elif lead.status != old_status:
            _log(lead, request.user, f"Status changed to {lead.get_status_display()}", True)
        messages.success(request, "Lead saved.")
        return redirect("lead_detail", pk=lead.pk)
    return render(request, "crm/form.html", {
        "page_title": "Edit lead" if pk else "Add lead", "nav": "", "active_business": lead.business_id, "form": form,
        "cancel_url": f"/leads/{pk}/" if pk else "/leads/", "submit_label": "Save lead", "is_lead": True})


@login_required
@require_POST
def lead_status(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    status = request.POST.get("status")
    if status in Lead.Status.values:
        today = timezone.localdate()
        if lead.set_status(status):
            if status == "trial" and not lead.trial_start:
                lead.trial_start = today
            if status == "booked" and not lead.booked_for:
                lead.booked_for = today
            if status == "lost" and request.POST.get("reason", "").strip():
                lead.lost_reason = request.POST["reason"].strip()[:250]
            if status != "new" and not lead.last_contacted:
                lead.last_contacted = today
            lead.save()
            _log(lead, request.user, f"Status changed to {lead.get_status_display()}", True)
            messages.success(request, f"{lead.name} marked {lead.get_status_display().lower()}.")
    else:
        messages.error(request, "Unknown status.")
    target = request.POST.get("next", "")
    return redirect(target if target.startswith("/") and not target.startswith("//") else f"/leads/{pk}/")


@login_required
@require_POST
def lead_note(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    body = request.POST.get("body", "").strip()
    if body and len(body) <= 5000:
        _log(lead, request.user, body)
        lead.last_contacted = timezone.localdate()
        if request.POST.get("follow_up"):
            try:
                lead.next_follow_up = timezone.localdate() + timedelta(days=int(request.POST["follow_up"]))
            except ValueError:
                pass
        lead.save()
        messages.success(request, "Note added.")
    else:
        messages.error(request, "Write a note of up to 5,000 characters.")
    return redirect("lead_detail", pk=pk)


@login_required
@require_POST
def lead_delete(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    business = lead.business
    lead.delete()
    messages.success(request, f"Deleted {lead.name}.")
    return redirect("business", slug=business.slug)


# --- businesses ------------------------------------------------------------

@login_required
def businesses(request):
    form = BusinessForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        business = form.save(commit=False)
        business.position = (Business.objects.order_by("-position").values_list("position", flat=True).first() or 0) + 1
        business.save()
        messages.success(request, f"{business.name} added.")
        return redirect("businesses")
    return render(request, "crm/businesses.html", {
        "page_title": "Businesses", "nav": "businesses", "form": form,
        "items": Business.objects.annotate(total=Count("leads")), })


@login_required
@require_POST
def business_delete(request, pk):
    business = get_object_or_404(Business, pk=pk)
    if business.leads.exists():
        messages.error(request, f"{business.name} still has leads. Move or delete them first.")
    else:
        business.delete()
        messages.success(request, f"{business.name} removed.")
    return redirect("businesses")


# --- account ---------------------------------------------------------------

@login_required
def account(request):
    partner_form, password_form = PartnerForm(), PasswordChangeForm(request.user)
    if request.method == "POST":
        if request.POST.get("action") == "partner" and request.user.is_staff:
            partner_form = PartnerForm(request.POST)
            with transaction.atomic():
                if User.objects.count() >= MAX_USERS:
                    partner_form.add_error(None, "Both seats are already in use.")
                elif partner_form.is_valid():
                    partner_form.save()
                    messages.success(request, "Partner added. Share their password privately.")
                    return redirect("account")
        elif request.POST.get("action") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                update_session_auth_hash(request, password_form.save())
                messages.success(request, "Password updated.")
                return redirect("account")
    return render(request, "crm/account.html", {"page_title": "Team & account", "nav": "account", "partner_form": partner_form,
                                                "password_form": password_form, "team": User.objects.all(), "seats_full": User.objects.count() >= MAX_USERS})


# --- export ----------------------------------------------------------------

def _safe(value):
    value = str(value if value is not None else "")
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


@login_required
def export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="leads-{timezone.localdate()}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Business", "Lead", "Contact", "Phone", "Email", "Location", "Source", "Status", "Handled by", "Deal value",
                     "Last contacted", "Next follow-up", "Trial start", "Trial end", "Booked for", "Lost reason", "Notes", "Added"])
    for l in _filtered(request):
        writer.writerow([_safe(v) for v in [l.business, l.name, l.contact_name, l.phone, l.email, l.location, l.source, l.get_status_display(),
                                            display(l.owner), l.value, l.last_contacted, l.next_follow_up, l.trial_start, l.trial_end,
                                            l.booked_for, l.lost_reason, l.notes, l.created_at.date()]])
    return response


def display(user):
    return user.get_full_name() or user.username
