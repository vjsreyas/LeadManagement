from django.contrib.auth.views import LogoutView
from django.urls import path

from crm import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("setup/", views.setup, name="setup"),
    path("login/", views.signin, name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("leads/", views.lead_list, name="leads"),
    path("b/<slug:slug>/", views.lead_list, name="business"),
    path("leads/new/", views.lead_edit, name="lead_new"),
    path("leads/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("leads/<int:pk>/edit/", views.lead_edit, name="lead_edit"),
    path("leads/<int:pk>/status/", views.lead_status, name="lead_status"),
    path("leads/<int:pk>/note/", views.lead_note, name="lead_note"),
    path("leads/<int:pk>/delete/", views.lead_delete, name="lead_delete"),
    path("businesses/", views.businesses, name="businesses"),
    path("businesses/<int:pk>/delete/", views.business_delete, name="business_delete"),
    path("account/", views.account, name="account"),
    path("export/leads.csv", views.export_csv, name="export_csv"),
]
