"""URL routing for the identity verification API endpoints."""

from django.urls import path

from identity.api import identity_start, identity_status

app_name = "identity"

urlpatterns = [
    path("start/", identity_start, name="start"),
    path("status/", identity_status, name="status"),
]
