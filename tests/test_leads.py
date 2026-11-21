from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.models import Business, Lead

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.a = User.objects.create_user("alex", password="pw-long-enough-1", first_name="Alex", is_staff=True)
        self.b = User.objects.create_user("sam", password="pw-long-enough-2", first_name="Sam")
        self.gyms = Business.objects.create(name="Gyms")
        self.re = Business.objects.create(name="Real estate")
        self.client.force_login(self.a)

    def lead(self, **kw):
        return Lead.objects.create(**{"business": self.gyms, "name": "Iron Gym", "owner": self.a, **kw})


class FlowTests(Base):
    def test_setup_redirect_when_no_users(self):
        User.objects.all().delete()
        self.client.logout()
        self.assertRedirects(self.client.get("/"), "/setup/")

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/leads/").status_code, 302)

    def test_dashboard_and_pages_render(self):
        lead = self.lead(status="trial", trial_start="2026-01-01")
        for url in ["/", "/leads/", f"/b/{self.gyms.slug}/", f"/leads/{lead.pk}/", f"/leads/{lead.pk}/edit/", "/leads/new/", "/businesses/", "/account/", "/export/leads.csv"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_business_slug_unique_and_add_clinics(self):
        r = self.client.post("/businesses/", {"name": "Clinics", "color": "#3b6fd4"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Business.objects.filter(slug="clinics").exists())
        self.assertEqual(Business.objects.create(name="Clinics!").slug, "clinics-2")

    def test_business_with_leads_cannot_be_deleted(self):
        self.lead()
        self.client.post(f"/businesses/{self.gyms.pk}/delete/")
        self.assertTrue(Business.objects.filter(pk=self.gyms.pk).exists())
        self.client.post(f"/businesses/{self.re.pk}/delete/")
        self.assertFalse(Business.objects.filter(pk=self.re.pk).exists())

    def test_everything_optional(self):
        r = self.client.post("/leads/new/", {"business": self.gyms.pk, "status": "lost", "value": ""})
        lead = Lead.objects.get()
        self.assertRedirects(r, f"/leads/{lead.pk}/")
        self.assertEqual((lead.name, lead.owner, lead.value), ("Unnamed lead", self.a, 0))
        self.assertIsNotNone(lead.closed_at)

    def test_social_links_optional_and_normalised(self):
        self.client.post("/leads/new/", {"business": self.gyms.pk, "status": "new", "instagram": "@ironparadise", "facebook": "facebook.com/iron", "linkedin": "https://linkedin.com/in/x"})
        lead = Lead.objects.get()
        self.assertEqual((lead.instagram, lead.facebook, lead.linkedin), ("https://instagram.com/ironparadise", "https://facebook.com/iron", "https://linkedin.com/in/x"))
        self.assertContains(self.client.get(f"/leads/{lead.pk}/"), 'href="https://instagram.com/ironparadise"')

    def test_blank_name_uses_phone(self):
        self.client.post("/leads/new/", {"business": self.gyms.pk, "status": "trial", "phone": "999"})
        self.assertEqual(Lead.objects.get().name, "999")

    def test_quick_status_change_sets_dates_and_logs(self):
        lead = self.lead()
        self.client.post(f"/leads/{lead.pk}/status/", {"status": "trial"})
        lead.refresh_from_db()
        self.assertEqual(lead.status, "trial")
        self.assertIsNotNone(lead.trial_start)
        self.assertIsNotNone(lead.last_contacted)
        self.client.post(f"/leads/{lead.pk}/status/", {"status": "won"})
        lead.refresh_from_db()
        self.assertIsNotNone(lead.closed_at)
        self.client.post(f"/leads/{lead.pk}/status/", {"status": "contacted"})
        lead.refresh_from_db()
        self.assertIsNone(lead.closed_at)
        self.assertEqual(lead.timeline.filter(is_status=True).count(), 3)

    def test_invalid_status_ignored(self):
        lead = self.lead()
        self.client.post(f"/leads/{lead.pk}/status/", {"status": "bogus"})
        lead.refresh_from_db()
        self.assertEqual(lead.status, "new")

    def test_status_redirect_blocks_open_redirect(self):
        lead = self.lead()
        r = self.client.post(f"/leads/{lead.pk}/status/", {"status": "contacted", "next": "//evil.example"})
        self.assertEqual(r["Location"], f"/leads/{lead.pk}/")

    def test_note_sets_follow_up(self):
        lead = self.lead()
        self.client.post(f"/leads/{lead.pk}/note/", {"body": "Called owner", "follow_up": "3"})
        lead.refresh_from_db()
        self.assertIsNotNone(lead.next_follow_up)
        self.assertEqual(lead.timeline.count(), 1)

    def test_filters_and_search(self):
        self.lead(name="Alpha Gym", status="trial")
        Lead.objects.create(business=self.re, name="Beta Realty", owner=self.b, status="won")
        def names(qs):
            return {l.name for l in self.client.get("/leads/" + qs).context["leads"]}
        self.assertEqual(names("?status=trial"), {"Alpha Gym"})
        self.assertEqual(names(f"?business={self.re.pk}"), {"Beta Realty"})
        self.assertEqual(names("?q=beta"), {"Beta Realty"})
        self.assertEqual(names(f"?owner={self.b.pk}"), {"Beta Realty"})
        self.assertEqual(names("?status=open"), {"Alpha Gym"})

    def test_business_section_only_shows_its_leads(self):
        self.lead(name="G1")
        Lead.objects.create(business=self.re, name="R1", owner=self.a)
        page = self.client.get(f"/b/{self.re.slug}/")
        self.assertEqual({l.name for l in page.context["leads"]}, {"R1"})

    def test_delete_lead(self):
        lead = self.lead()
        self.client.post(f"/leads/{lead.pk}/delete/")
        self.assertFalse(Lead.objects.exists())

    def test_two_seat_limit(self):
        data = {"action": "partner", "first_name": "Z", "username": "zed", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99"}
        self.client.post("/account/", data)
        self.assertFalse(User.objects.filter(username="zed").exists())

    def test_csv_export_escapes_formulas(self):
        self.lead(name="=cmd()")
        body = self.client.get("/export/leads.csv").content.decode()
        self.assertIn("'=cmd()", body)

    def test_health(self):
        self.client.logout()
        self.assertEqual(self.client.get("/health/").json(), {"status": "ok"})


@override_settings(SETUP_TOKEN="tok")
class SetupTests(TestCase):
    def test_setup_creates_owner_and_default_businesses(self):
        data = {"first_name": "Alex", "username": "alex", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99", "setup_token": "tok"}
        self.assertEqual(self.client.post("/setup/", data).status_code, 302)
        self.assertTrue(User.objects.get(username="alex").is_staff)
        self.assertEqual(list(Business.objects.values_list("name", flat=True)), ["Gyms", "Real estate", "Clinics"])
        self.assertEqual(self.client.get("/setup/").status_code, 302)
