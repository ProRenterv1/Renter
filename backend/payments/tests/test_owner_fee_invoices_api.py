from datetime import date

import pytest
from rest_framework.test import APIClient

from payments.models import OwnerFeeTaxInvoice

pytestmark = pytest.mark.django_db


def _auth_client(user):
    client = APIClient()
    resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_owner_fee_invoices_list_filters_owner(owner_user, other_user):
    OwnerFeeTaxInvoice.objects.create(
        owner=owner_user,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        fee_subtotal="10.00",
        gst="0.50",
        total="10.50",
        invoice_number="INV-202501-1-001",
    )
    OwnerFeeTaxInvoice.objects.create(
        owner=other_user,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        fee_subtotal="20.00",
        gst="1.00",
        total="21.00",
        invoice_number="INV-202501-2-001",
    )

    client = _auth_client(owner_user)
    resp = client.get("/api/owner/payouts/fee-invoices/")

    assert resp.status_code == 200, resp.data
    assert len(resp.data["results"]) == 1
    assert resp.data["results"][0]["invoice_number"] == "INV-202501-1-001"


def test_owner_fee_invoice_download_requires_owner(owner_user, other_user):
    invoice = OwnerFeeTaxInvoice.objects.create(
        owner=other_user,
        period_start=date(2025, 2, 1),
        period_end=date(2025, 2, 28),
        fee_subtotal="10.00",
        gst="0.50",
        total="10.50",
        invoice_number="INV-202502-2-001",
        pdf_s3_key="uploads/private/fee-invoices/INV-202502-2-001.pdf",
    )

    client = _auth_client(owner_user)
    resp = client.get(f"/api/owner/payouts/fee-invoices/{invoice.id}/download/")

    assert resp.status_code == 404


def test_owner_fee_invoice_download_returns_url(owner_user):
    invoice = OwnerFeeTaxInvoice.objects.create(
        owner=owner_user,
        period_start=date(2025, 3, 1),
        period_end=date(2025, 3, 31),
        fee_subtotal="12.00",
        gst="0.60",
        total="12.60",
        invoice_number="INV-202503-1-001",
        pdf_s3_key="uploads/private/fee-invoices/INV-202503-1-001.pdf",
    )

    client = _auth_client(owner_user)
    resp = client.get(f"/api/owner/payouts/fee-invoices/{invoice.id}/download/")

    assert resp.status_code == 200, resp.data
    assert "url" in resp.data
