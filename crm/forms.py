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
        fields = ["business", "name", "contact_name", "phone", "email", "location", "instagram", "facebook", "linkedin", "website", "source", "owner", "status", "value",
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
        for f, ph in (("instagram", "instagram.com/… or @handle"), ("facebook", "facebook.com/…"), ("linkedin", "linkedin.com/in/…"), ("website", "example.com")):
            self.fields[f].widget.attrs["placeholder"] = ph
        self.fields["owner"].required = False
        self.fields["owner"].empty_label = "Me"

    def clean_value(self):
        return self.cleaned_data.get("value") or 0


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
