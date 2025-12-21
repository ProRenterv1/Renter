import importlib
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework.test import APIClient

import renter.urls as renter_urls
from bookings.models import Booking
from disputes.models import DisputeCase, DisputeEvidence, DisputeMessage
from listings.models import Listing
from operator_core.models import OperatorAuditEvent

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def enable_operator_routes(settings):
    original_enable = settings.ENABLE_OPERATOR
    original_hosts = getattr(settings, "OPS_ALLOWED_HOSTS", [])
    original_allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))

    settings.ENABLE_OPERATOR = True
    settings.OPS_ALLOWED_HOSTS = ["ops.example.com"]
    settings.ALLOWED_HOSTS = ["ops.example.com", "public.example.com", "testserver"]
    clear_url_caches()
    importlib.reload(renter_urls)
    yield
    settings.ENABLE_OPERATOR = original_enable
    settings.OPS_ALLOWED_HOSTS = original_hosts
    settings.ALLOWED_HOSTS = original_allowed_hosts
    clear_url_caches()
    importlib.reload(renter_urls)


@pytest.fixture
def operator_user():
    group, _ = Group.objects.get_or_create(name="operator_support")
    user = User.objects.create_user(
        username="operator",
        email="operator@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def staff_user_no_group():
    return User.objects.create_user(
        username="staff-nogroup",
        email="staff-nogroup@example.com",
        password="pass123",
        is_staff=True,
    )


@pytest.fixture
def renter_user():
    return User.objects.create_user(
        username="renter",
        email="renter@example.com",
        password="pass123",
    )


@pytest.fixture
def owner_user():
    return User.objects.create_user(
        username="owner",
        email="owner@example.com",
        password="pass123",
    )


@pytest.fixture
def booking(owner_user, renter_user):
    listing = Listing.objects.create(
        owner=owner_user,
        title="Drill",
        description="desc",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        postal_code="T0T0T0",
    )
    return Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=datetime.utcnow().date(),
        end_date=(datetime.utcnow() + timedelta(days=1)).date(),
        status=Booking.Status.PAID,
        charge_payment_intent_id="pi_charge_test",
        deposit_hold_id="pi_deposit_test",
        deposit_locked=True,
        is_disputed=True,
        totals={"damage_deposit": "100.00"},
    )


@pytest.fixture
def dispute(booking, operator_user):
    return DisputeCase.objects.create(
        booking=booking,
        opened_by=operator_user,
        opened_by_role=DisputeCase.OpenedByRole.OWNER,
        category=DisputeCase.Category.DAMAGE,
        description="Issue",
        status=DisputeCase.Status.OPEN,
    )


def _authed_client(user):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)
    return client


def test_permissions_require_operator_group(dispute, staff_user_no_group, renter_user):
    client = _authed_client(renter_user)
    resp = client.get("/api/operator/disputes/")
    assert resp.status_code in (401, 403)

    client = _authed_client(staff_user_no_group)
    resp = client.get("/api/operator/disputes/")
    assert resp.status_code == 403


def test_reason_required_for_mutations(dispute, operator_user):
    client = _authed_client(operator_user)
    resp = client.post(f"/api/operator/disputes/{dispute.id}/start-review/", {})
    assert resp.status_code == 400

    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/request-more-evidence/",
        {"message": "need more", "due_at": timezone.now().isoformat()},
    )
    assert resp.status_code == 400


def test_start_review_sets_status_and_audits(dispute, operator_user):
    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/start-review/",
        {"reason": "review"},
        format="json",
    )
    assert resp.status_code == 200
    dispute.refresh_from_db()
    assert dispute.status == DisputeCase.Status.UNDER_REVIEW
    assert OperatorAuditEvent.objects.filter(
        action="operator.dispute.start_review", entity_id=str(dispute.id)
    ).exists()


def test_request_more_evidence_updates_due_and_message(dispute, operator_user):
    client = _authed_client(operator_user)
    due_at = timezone.now() + timedelta(hours=4)
    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/request-more-evidence/",
        {"reason": "need evidence", "message": "upload", "due_at": due_at.isoformat()},
        format="json",
    )
    assert resp.status_code == 200
    dispute.refresh_from_db()
    assert dispute.status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE
    assert abs(dispute.intake_evidence_due_at - due_at) < timedelta(seconds=1)
    assert DisputeMessage.objects.filter(dispute=dispute, text="upload").exists()
    assert OperatorAuditEvent.objects.filter(
        action="operator.dispute.request_more_evidence"
    ).exists()


def test_close_as_duplicate_finalizes_booking(dispute, operator_user):
    booking = dispute.booking
    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/close-as-duplicate/",
        {"reason": "dup", "duplicate_of_id": 99, "message": "dup"},
        format="json",
    )
    assert resp.status_code == 200
    dispute.refresh_from_db()
    booking.refresh_from_db()
    assert dispute.status == DisputeCase.Status.CLOSED_AUTO
    assert booking.is_disputed is False
    assert booking.deposit_locked is False


def test_close_as_late_finalizes_booking(dispute, operator_user):
    booking = dispute.booking
    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/close-as-late/",
        {"reason": "late"},
        format="json",
    )
    assert resp.status_code == 200
    dispute.refresh_from_db()
    booking.refresh_from_db()
    assert dispute.status == DisputeCase.Status.CLOSED_AUTO
    assert booking.is_disputed is False
    assert booking.deposit_locked is False


def test_resolve_invokes_settlement_and_updates_fields(monkeypatch, dispute, operator_user):
    booking = dispute.booking
    called = {}

    def _refund(booking_arg, amount_cents):
        called["refund"] = amount_cents
        return "re_123"

    def _capture(booking_arg, amount_cents):
        called["capture"] = amount_cents
        return "pi_cap"

    def _release(booking_arg):
        called["release"] = True
        return True

    monkeypatch.setattr("disputes.services.settlement.refund_booking_charge", _refund)
    monkeypatch.setattr("disputes.services.settlement.capture_deposit_amount_cents", _capture)
    monkeypatch.setattr("disputes.services.settlement.release_deposit_hold_if_needed", _release)

    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/resolve/",
        {
            "reason": "resolve",
            "decision": "resolved_owner",
            "refund_amount_cents": 100,
            "deposit_capture_amount_cents": 200,
            "decision_notes": "done",
        },
        format="json",
    )
    assert resp.status_code == 200
    dispute.refresh_from_db()
    booking.refresh_from_db()
    assert dispute.status == DisputeCase.Status.RESOLVED_OWNER
    assert dispute.refund_amount_cents == 100
    assert dispute.deposit_capture_amount_cents == 200
    assert booking.is_disputed is False
    assert booking.deposit_locked is False
    assert called["refund"] == 100
    assert called["capture"] == 200
    assert called["release"] is True
    assert OperatorAuditEvent.objects.filter(
        action="operator.dispute.resolve", entity_id=str(dispute.id)
    ).exists()


def test_evidence_presign_requires_reason_and_audits(dispute, operator_user):
    evidence = DisputeEvidence.objects.create(
        dispute=dispute,
        uploaded_by=operator_user,
        kind=DisputeEvidence.Kind.PHOTO,
        s3_key="evidence/key.jpg",
    )
    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/evidence/{evidence.id}/presign-get/",
        {},
        format="json",
    )
    assert resp.status_code == 400

    resp = client.post(
        f"/api/operator/disputes/{dispute.id}/evidence/{evidence.id}/presign-get/",
        {"reason": "download"},
        format="json",
    )
    assert resp.status_code == 200
    assert "url" in resp.data
    assert OperatorAuditEvent.objects.filter(
        action="operator.dispute.evidence.presign_get"
    ).exists()
