from django.urls import path

from . import api

app_name = "payments_owner_payouts"

urlpatterns = [
    path("summary/", api.owner_payouts_summary, name="owner_payouts_summary"),
    path("history/", api.owner_payouts_history, name="owner_payouts_history"),
    path("fee-invoices/", api.owner_fee_invoices_list, name="owner_fee_invoices_list"),
    path(
        "fee-invoices/<int:invoice_id>/download/",
        api.owner_fee_invoice_download,
        name="owner_fee_invoice_download",
    ),
    path(
        "start-onboarding/",
        api.owner_payouts_start_onboarding,
        name="owner_payouts_start_onboarding",
    ),
    path("bank-details/", api.owner_payouts_update_bank_details, name="owner_payouts_bank_details"),
    path("instant-payout/", api.owner_payouts_instant_payout, name="owner_payouts_instant_payout"),
]
