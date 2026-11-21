from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Business, Lead

User = get_user_model()


def person(user):
    return user.get_full_name() or user.username


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["business", "name", "contact_name", "phone", "email", "location", "source", "owner", "status", "value",
                  "last_contacted", "next_follow_up", "trial_start", "trial_end", "booked_for", "lost_reason", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4, "placeholder": "What was said, what they need, what to do next"}),
                   **{f: forms.DateInput(attrs={"type": "date"}) for f in
                      ("last_contacted", "next_follow_up", "trial_start", "trial_end", "booked_for")}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = User.objects.filter(is_active=True)
        self.fields["owner"].label_from_instance = person
        self.fields["owner"].label = "Handled by"
        self.fields["business"].empty_label = None
        self.fields["source"].required = False

    def clean(self):
        data = super().clean()
        status = data.get("status")
        if status == Lead.Status.LOST and not (data.get("lost_reason") or "").strip():
            self.add_error("lost_reason", "Note why this lead was lost.")
        if status == Lead.Status.TRIAL and not data.get("trial_start"):
            self.add_error("trial_start", "Add the trial start date.")
        if status == Lead.Status.BOOKED and not data.get("booked_for"):
            self.add_error("booked_for", "Add the booking date.")
        return data


class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ["name", "color"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Business.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise ValidationError("You already have a business with that name.")
        return name


class PartnerForm(UserCreationForm):
    first_name = forms.CharField(max_length=60, label="Full name")
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "username", "email", "password1", "password2"]

    def clean_username(self):
        value = super().clean_username()
        if User.objects.filter(username__iexact=value).exists():
            raise ValidationError("That username is already in use.")
        return value


class SetupForm(PartnerForm):
    setup_token = forms.CharField(required=False, widget=forms.PasswordInput, label="Setup token",
                                  help_text="SETUP_TOKEN from your Render environment. Not needed locally in debug mode.")
