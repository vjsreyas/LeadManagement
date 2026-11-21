from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Business(models.Model):
    """A line of business we sell into, e.g. Gyms, Real estate, Clinics."""

    COLORS = [("#2f7d6b", "Green"), ("#3b6fd4", "Blue"), ("#c2571a", "Orange"), ("#8a4fbf", "Purple"),
              ("#c23b5a", "Rose"), ("#a07a00", "Gold"), ("#4a5568", "Slate")]

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, editable=False)
    color = models.CharField(max_length=7, choices=COLORS, default="#2f7d6b")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "businesses"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "business"
            slug, n = base, 2
            while Business.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        INTERESTED = "interested", "Interested"
        TRIAL = "trial", "In trial"
        BOOKED = "booked", "Booked"
        WON = "won", "Closed won"
        LOST = "lost", "Closed lost"

    # Statuses that mean the lead is still being worked.
    OPEN = ["new", "contacted", "interested", "trial", "booked"]
    SOURCES = [(s, s) for s in ["Walk-in", "Cold call", "WhatsApp", "Instagram", "Referral", "Website", "Other"]]

    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="leads")
    name = models.CharField("Lead / business name", max_length=120)
    contact_name = models.CharField("Contact person", max_length=120, blank=True)
    phone = models.CharField(max_length=35, blank=True)
    email = models.EmailField(blank=True)
    location = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=30, choices=SOURCES, default="Cold call", blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leads")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    value = models.DecimalField("Deal value", max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    last_contacted = models.DateField(null=True, blank=True)
    next_follow_up = models.DateField("Next follow-up", null=True, blank=True)
    trial_start = models.DateField(null=True, blank=True)
    trial_end = models.DateField(null=True, blank=True)
    booked_for = models.DateField("Booked for", null=True, blank=True)
    lost_reason = models.CharField(max_length=250, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        return self.status in self.OPEN

    @property
    def follow_up_overdue(self):
        return bool(self.is_open and self.next_follow_up and self.next_follow_up < timezone.localdate())

    def clean(self):
        if self.trial_start and self.trial_end and self.trial_end < self.trial_start:
            raise ValidationError({"trial_end": "Trial end cannot be before its start."})

    def set_status(self, status):
        """Change status, keeping closed_at consistent. Returns True if it changed."""
        if status == self.status:
            return False
        self.status = status
        self.closed_at = timezone.now() if status in (self.Status.WON, self.Status.LOST) else None
        return True


class LeadNote(models.Model):
    """Timeline entry: a typed note, or an automatic record of a status change."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="timeline")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    body = models.TextField(max_length=5000)
    is_status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    last_attempt = models.DateTimeField(default=timezone.now)
