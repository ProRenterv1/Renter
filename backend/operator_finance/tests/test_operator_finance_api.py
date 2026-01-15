import importlib
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

import renter.urls as renter_urls
from bookings.models import Booking
from core.settings_resolver import clear_settings_cache
from disputres.services import settlement
from operator_bookings.models import BookingEvent
from operator_core.models import OperatorAuditEvent
from operator_settings.models import DbSetting
from payments.models import Transaction

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
    settings.STRIPE_SECRET_KEY = "sk_test"
    clear_url_caches()
    importlib.reload(renter_urls)
    yield
    settings.ENABLE_OPERATOR = original_enable
    settings.OPS_ALLOWED_HOSTS = original_hosts
    settings.ALLOWED_HOSTS = original_allowed_hosts
    clear_url_caches()
    importlib.reload(renter_urls)


@pytest.fixture
def operator_finance_user():
    group, _ = Group.objects.get_or_create(name="operator_finance")
    user = User.objects.create_user(
        username="finance",
        email="finance@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def operator_admin_user():
    group, _ = Group.objects.get_or_create(name="operator_admin")
    user = User.objects.create_user(
        username="admin",
        email="admin@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def staff_user():
    group, _ = Group.objects.get_or_create(name="operator_support")
    user = User.objects.create_user(
        username="support",
        email="support@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


def _ops_client(user=None):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    if user:
        client.force_authenticate(user=user)
    return client


def _results(resp):
    return (
        resp.data["results"]
        if isinstance(resp.data, dict) and "results" in resp.data
        else resp.data
    )


def test_permissions_non_staff_forbidden(renter_user):
    client = _ops_client(renter_user)
    resp = client.get("/api/operator/transactions/")
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_permissions_staff_without_role_forbidden(staff_user):
    client = _ops_client(staff_user)
    resp = client.get("/api/operator/transactions/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_permissions_finance_allowed(operator_finance_user):
    client = _ops_client(operator_finance_user)
    resp = client.get("/api/operator/transactions/")
    assert resp.status_code == status.HTTP_200_OK


def test_transactions_list_filters_and_ordering(
    operator_finance_user, booking_factory, renter_user, other_user
):
    booking_a = booking_factory(status=Booking.Status.PAID)
    booking_b = booking_factory(renter=other_user, status=Booking.Status.PAID)

    now = timezone.now()
    older = now - timedelta(days=1)

    tx1 = Transaction.objects.create(
        user=renter_user,
        booking=booking_a,
        kind=Transaction.Kind.BOOKING_CHARGE,
        amount="10.00",
        stripe_id="pi_1",
    )
    Transaction.objects.filter(pk=tx1.pk).update(created_at=older)

    tx2 = Transaction.objects.create(
        user=other_user,
        booking=booking_b,
        kind=Transaction.Kind.REFUND,
        amount="5.00",
        stripe_id="re_1",
    )

    tx3 = Transaction.objects.create(
        user=other_user,
        booking=booking_a,
        kind=Transaction.Kind.PLATFORM_FEE,
        amount="2.00",
        stripe_id="fee_1",
    )
    Transaction.objects.filter(pk=tx3.pk).update(created_at=now + timedelta(minutes=1))

    client = _ops_client(operator_finance_user)
    resp = client.get("/api/operator/transactions/")
    assert resp.status_code == status.HTTP_200_OK
    data = _results(resp)
    assert [row["id"] for row in data] == [tx3.id, tx2.id, tx1.id]

    resp_kind = client.get("/api/operator/transactions/", {"kind": Transaction.Kind.REFUND})
    assert [row["id"] for row in _results(resp_kind)] == [tx2.id]

    resp_booking = client.get("/api/operator/transactions/", {"booking": booking_a.id})
    ids_booking = [row["id"] for row in _results(resp_booking)]
    assert tx3.id in ids_booking and tx1.id in ids_booking and tx2.id not in ids_booking

    resp_user = client.get("/api/operator/transactions/", {"user": other_user.id})
    ids_user = [row["id"] for row in _results(resp_user)]
    assert set(ids_user) == {tx2.id, tx3.id}

    resp_range = client.get(
        "/api/operator/transactions/",
        {
            "created_at_after": (now - timedelta(hours=1)).isoformat(),
            "created_at_before": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert [row["id"] for row in _results(resp_range)] == [tx3.id, tx2.id]


def test_booking_finance_read(operator_finance_user, booking_factory):
    booking = booking_factory(
        status=Booking.Status.PAID,
        charge_payment_intent_id="pi_charge",
        deposit_hold_id="pi_deposit",
    )
    tx1 = Transaction.objects.create(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.BOOKING_CHARGE,
        amount="10.00",
        stripe_id="pi_charge",
    )
    tx2 = Transaction.objects.create(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        amount="3.00",
        stripe_id="pi_deposit",
    )

    client = _ops_client(operator_finance_user)
    resp = client.get(f"/api/operator/bookings/{booking.id}/finance")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["booking_id"] == booking.id
    assert resp.data["stripe"]["charge_payment_intent_id"] == "pi_charge"
    assert resp.data["stripe"]["deposit_hold_id"] == "pi_deposit"
    ledger_ids = [entry["id"] for entry in resp.data["ledger"]]
    assert set(ledger_ids) == {tx1.id, tx2.id}


def test_refund_action_creates_audit_event_and_is_idempotent(
    operator_finance_user, booking_factory, monkeypatch
):
    booking = booking_factory(
        status=Booking.Status.PAID, charge_payment_intent_id="pi_charge", deposit_hold_id=""
    )
    client = _ops_client(operator_finance_user)

    monkeypatch.setattr("disputres.services.settlement._get_stripe_api_key", lambda: "sk_test")

    def _refund_create(**kwargs):
        return SimpleNamespace(id="re_123", amount=500)

    with patch("stripe.Refund.create", side_effect=_refund_create):
        resp = client.post(
            f"/api/operator/bookings/{booking.id}/refund",
            {"amount": "5.00", "reason": "duplicate charge", "notify_user": True},
            format="json",
        )
    assert resp.status_code == status.HTTP_200_OK, resp.data
    assert Transaction.objects.filter(kind=Transaction.Kind.REFUND).count() == 1
    assert OperatorAuditEvent.objects.filter(
        entity_id=str(booking.id), action="operator.booking.refund"
    ).exists()
    event = BookingEvent.objects.filter(booking=booking, payload__action="finance_refund").first()
    assert event is not None

    # Retry should not duplicate refund transaction
    with patch("stripe.Refund.create", side_effect=_refund_create):
        client.post(
            f"/api/operator/bookings/{booking.id}/refund",
            {"amount": "5.00", "reason": "duplicate charge"},
            format="json",
        )
    assert Transaction.objects.filter(kind=Transaction.Kind.REFUND).count() == 1


def test_deposit_capture_action_idempotent(operator_finance_user, booking_factory, monkeypatch):
    booking = booking_factory(
        status=Booking.Status.PAID,
        deposit_hold_id="pi_deposit",
        charge_payment_intent_id="pi_charge",
    )
    client = _ops_client(operator_finance_user)
    monkeypatch.setattr("disputres.services.settlement._get_stripe_api_key", lambda: "sk_test")
    monkeypatch.setattr("payments.stripe_api._get_stripe_api_key", lambda: "sk_test")

    class DummyIntent:
        status = "requires_capture"

    with (
        patch("stripe.PaymentIntent.retrieve", return_value=DummyIntent()),
        patch("stripe.PaymentIntent.capture", return_value=SimpleNamespace(id="pi_deposit")),
    ):
        resp = client.post(
            f"/api/operator/bookings/{booking.id}/deposit/capture",
            {"amount": "4.00", "reason": "damage"},
            format="json",
        )
    assert resp.status_code == status.HTTP_200_OK, resp.data
    assert Transaction.objects.filter(kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE).count() == 1

    with (
        patch("stripe.PaymentIntent.retrieve", return_value=DummyIntent()),
        patch("stripe.PaymentIntent.capture", return_value=SimpleNamespace(id="pi_deposit")),
    ):
        client.post(
            f"/api/operator/bookings/{booking.id}/deposit/capture",
            {"amount": "4.00", "reason": "damage"},
            format="json",
        )
    assert Transaction.objects.filter(kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE).count() == 1


def test_deposit_release_action_idempotent(operator_finance_user, booking_factory, monkeypatch):
    booking = booking_factory(
        status=Booking.Status.PAID,
        deposit_hold_id="pi_deposit",
        charge_payment_intent_id="pi_charge",
        totals={"damage_deposit": "10.00"},
    )
    client = _ops_client(operator_finance_user)
    monkeypatch.setattr("payments.stripe_api._get_stripe_api_key", lambda: "sk_test")

    class DummyIntent:
        status = "requires_capture"

    with (
        patch("stripe.PaymentIntent.retrieve", return_value=DummyIntent()),
        patch("stripe.PaymentIntent.cancel", return_value=SimpleNamespace(id="pi_deposit")),
    ):
        resp = client.post(
            f"/api/operator/bookings/{booking.id}/deposit/release",
            {"reason": "resolved"},
            format="json",
        )
    assert resp.status_code == status.HTTP_200_OK, resp.data
    assert Transaction.objects.filter(kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE).count() == 1

    with (
        patch("stripe.PaymentIntent.retrieve", return_value=DummyIntent()),
        patch("stripe.PaymentIntent.cancel", return_value=SimpleNamespace(id="pi_deposit")),
    ):
        client.post(
            f"/api/operator/bookings/{booking.id}/deposit/release",
            {"reason": "resolved"},
            format="json",
        )
    assert Transaction.objects.filter(kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE).count() == 1


def test_settlement_refund_idempotent(monkeypatch, booking_factory):
    booking = booking_factory(
        status=Booking.Status.PAID, charge_payment_intent_id="pi_charge", deposit_hold_id=""
    )
    monkeypatch.setattr("disputres.services.settlement._get_stripe_api_key", lambda: "sk_test")

    def _refund_create(**kwargs):
        return SimpleNamespace(id="re_idem", amount=500)

    with patch("stripe.Refund.create", side_effect=_refund_create):
        settlement.refund_booking_charge(booking, 500, dispute_id="dispute-1")
    with patch("stripe.Refund.create", side_effect=_refund_create):
        settlement.refund_booking_charge(booking, 500, dispute_id="dispute-1")

    refunds = Transaction.objects.filter(kind=Transaction.Kind.REFUND, stripe_id="re_idem")
    assert refunds.count() == 1


def test_settlement_transfer_idempotent(monkeypatch, booking_factory, owner_user):
    booking = booking_factory(
        status=Booking.Status.PAID,
        deposit_hold_id="pi_deposit",
        charge_payment_intent_id="pi_charge",
    )
    booking.owner = owner_user
    booking.save(update_fields=["owner"])

    monkeypatch.setattr("disputres.services.settlement._get_stripe_api_key", lambda: "sk_test")
    monkeypatch.setattr(
        "disputres.services.settlement.ensure_connect_account",
        lambda _user: SimpleNamespace(stripe_account_id="acct_123", charges_enabled=True),
    )

    def _transfer_create(**kwargs):
        return {"id": "tr_123"}

    with patch("stripe.Transfer.create", side_effect=_transfer_create):
        settlement.transfer_damage_award_to_owner(booking, 700, dispute_id="case-1")
    with patch("stripe.Transfer.create", side_effect=_transfer_create):
        settlement.transfer_damage_award_to_owner(booking, 700, dispute_id="case-1")

    transfers = Transaction.objects.filter(kind=Transaction.Kind.OWNER_EARNING, stripe_id="tr_123")
    assert transfers.count() == 1


def test_settlement_transfer_gst_split_idempotent(
    monkeypatch, booking_factory, owner_user, settings
):
    platform_user = User.objects.create_user(
        username="platform-ledger-gst", password="x", can_list=False, can_rent=False
    )
    settings.PLATFORM_LEDGER_USER_ID = platform_user.id
    DbSetting.objects.create(
        key="ORG_GST_NUMBER",
        value_json="123456789RT0001",
        value_type="str",
    )
    DbSetting.objects.create(
        key="ORG_GST_REGISTERED",
        value_json=True,
        value_type="bool",
    )
    clear_settings_cache()

    booking = booking_factory(
        status=Booking.Status.PAID,
        deposit_hold_id="pi_deposit",
        charge_payment_intent_id="pi_charge",
    )
    booking.owner = owner_user
    booking.save(update_fields=["owner"])

    monkeypatch.setattr("disputres.services.settlement._get_stripe_api_key", lambda: "sk_test")
    monkeypatch.setattr(
        "disputres.services.settlement.ensure_connect_account",
        lambda _user: SimpleNamespace(stripe_account_id="acct_123", charges_enabled=True),
    )

    def _transfer_create(**kwargs):
        return {"id": "tr_gst_1"}

    with patch("stripe.Transfer.create", side_effect=_transfer_create):
        settlement.transfer_damage_award_to_owner(booking, 1000, dispute_id="case-gst")
    with patch("stripe.Transfer.create", side_effect=_transfer_create):
        settlement.transfer_damage_award_to_owner(booking, 1000, dispute_id="case-gst")

    platform_fee = Transaction.objects.filter(
        user=platform_user,
        kind=Transaction.Kind.PLATFORM_FEE,
        stripe_id="tr_gst_1",
    )
    gst_collected = Transaction.objects.filter(
        user=platform_user,
        kind=Transaction.Kind.GST_COLLECTED,
        stripe_id="tr_gst_1",
    )
    assert platform_fee.count() == 1
    assert gst_collected.count() == 1
    assert platform_fee.first().amount == Decimal("9.52")
    assert gst_collected.first().amount == Decimal("0.48")


def test_exports_csv(operator_finance_user, booking_factory, renter_user):
    booking = booking_factory(status=Booking.Status.PAID)
    now = timezone.now()
    tx_platform = Transaction.objects.create(
        user=renter_user,
        booking=booking,
        kind=Transaction.Kind.PLATFORM_FEE,
        amount="3.00",
        currency="cad",
        stripe_id="fee_1",
    )
    Transaction.objects.filter(pk=tx_platform.pk).update(created_at=now)
    tx_promo = Transaction.objects.create(
        user=renter_user,
        booking=booking,
        kind=Transaction.Kind.PROMOTION_CHARGE,
        amount="4.00",
        currency="cad",
        stripe_id="promo_1",
    )
    Transaction.objects.filter(pk=tx_promo.pk).update(created_at=now)

    client = _ops_client(operator_finance_user)
    resp = client.get(
        "/api/operator/exports/platform-revenue.csv",
        {
            "from": (now - timedelta(days=1)).date().isoformat(),
            "to": (now + timedelta(days=1)).date().isoformat(),
        },
    )
    assert resp.status_code == status.HTTP_200_OK
    content = resp.content.decode().strip().splitlines()
    header = content[0].split(",")
    assert header == ["created_at", "source", "booking_id", "txn_id", "amount", "currency"]
    body = "\n".join(content[1:])
    assert Transaction.Kind.PLATFORM_FEE in body
    assert Transaction.Kind.PROMOTION_CHARGE in body


def test_owner_ledger_export_filters_by_owner(
    operator_finance_user, booking_factory, owner_user, other_user
):
    booking = booking_factory(owner=owner_user, status=Booking.Status.PAID)
    other_booking = booking_factory(owner=other_user, status=Booking.Status.PAID)

    tx_owner = Transaction.objects.create(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount="8.00",
        stripe_id="tr_owner",
    )
    Transaction.objects.create(
        user=other_user,
        booking=other_booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount="5.00",
        stripe_id="tr_other",
    )

    client = _ops_client(operator_finance_user)
    resp = client.get(
        "/api/operator/exports/owner-ledger.csv",
        {"owner_id": owner_user.id, "from": timezone.localdate().isoformat()},
    )
    assert resp.status_code == status.HTTP_200_OK
    body = resp.content.decode()
    assert str(tx_owner.id) in body
    assert "tr_other" not in body
