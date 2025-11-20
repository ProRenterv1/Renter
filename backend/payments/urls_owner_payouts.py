from django.urls import path

from . import api

app_name = "payments_owner_payouts"

urlpatterns = [
    path("summary/", api.owner_payouts_summary, name="owner_payouts_summary"),
    path("history/", api.owner_payouts_history, name="owner_payouts_history"),
    path(
        "start-onboarding/",
        api.owner_payouts_start_onboarding,
        name="owner_payouts_start_onboarding",
    ),
]
