from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from bookings.models import Booking
from bookings.tasks import authorize_deposit_for_start_day, enqueue_deposit_authorizations
from payments.models import Transaction
from payments.stripe_api import DepositAuthorizationInsufficientFunds, stripe_webhook

pytestmark = pytest.mark.django_db


def _auth_client(user) -> APIClient:
    client = APIClient()
    token_resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_resp.data['access']}")
    return client


def test_pay_does_not_authorize_deposit(monkeypatch, renter_user, listing):
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=1)
    booking = Booking.objects.create(
        listing=listing,
        owner=listing.owner,
        renter=renter_user,
        start_date=start,
        end_date=end,
        status=Booking.Status.CONFIRMED,
        totals={
            "rental_subtotal": "80.00",
            "service_fee": "10.00",
            "damage_deposit": "50.00",
        },
    )

    monkeypatch.setattr(
        "bookings.api.ensure_stripe_customer", lambda user, customer_id=None: "cus_pay"
    )

    created_calls = []

    def fake_create_charge(*, booking, customer_id, payment_method_id):
        created_calls.append((booking.id, customer_id, payment_method_id))
        return "pi_charge_only"

    monkeypatch.setattr("bookings.api.create_booking_charge_intent", fake_create_charge)

    client = _auth_client(renter_user)
    resp = client.post(
        f"/api/bookings/{booking.id}/pay/",
        {"stripe_payment_method_id": "pm_test", "stripe_customer_id": "cus_pay"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.deposit_hold_id == ""
    assert booking.deposit_authorized_at is None
    assert booking.renter_stripe_customer_id == "cus_pay"
    assert booking.renter_stripe_payment_method_id == "pm_test"
    assert created_calls == [(booking.id, "cus_pay", "pm_test")]


def test_deposit_authorizes_on_start_day(monkeypatch, booking_factory):
    today = date.today()
    booking = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        totals={
            "rental_subtotal": "100.00",
            "service_fee": "20.00",
            "damage_deposit": "50.00",
        },
    )
    booking.renter_stripe_customer_id = "cus_start"
    booking.renter_stripe_payment_method_id = "pm_start"
    booking.charge_payment_intent_id = "pi_charge_start"
    booking.save(
        update_fields=[
            "renter_stripe_customer_id",
            "renter_stripe_payment_method_id",
            "charge_payment_intent_id",
        ]
    )

    enqueued: list[int] = []
    monkeypatch.setattr(
        "bookings.tasks.authorize_deposit_for_start_day.delay",
        lambda booking_id: enqueued.append(booking_id),
    )
    monkeypatch.setattr("bookings.tasks.timezone.localdate", lambda: today)

    enqueue_deposit_authorizations()
    assert enqueued == [booking.id]

    def fake_create_deposit_hold(*, booking, customer_id, payment_method_id):
        booking.deposit_hold_id = "pi_deposit_success"
        booking.save(update_fields=["deposit_hold_id"])
        return "pi_deposit_success"

    monkeypatch.setattr(
        "bookings.tasks.create_booking_deposit_hold_intent",
        fake_create_deposit_hold,
    )
    monkeypatch.setattr("bookings.tasks.timezone.localdate", lambda: today)
    monkeypatch.setattr(
        "bookings.tasks.timezone.now",
        lambda: timezone.make_aware(datetime(today.year, today.month, today.day, 8, 0)),
    )

    success = authorize_deposit_for_start_day(booking.id)
    assert success is True

    booking.refresh_from_db()
    assert booking.deposit_hold_id == "pi_deposit_success"
    assert booking.deposit_authorized_at is not None
    assert booking.deposit_attempt_count == 1


def test_deposit_retry_then_cancel(monkeypatch, booking_factory, owner_user, renter_user, settings):
    today = date.today()
    booking = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        totals={
            "rental_subtotal": "120.00",
            "service_fee": "0.00",
            "owner_fee": "6.00",
            "platform_fee_total": "6.00",
            "owner_payout": "114.00",
            "damage_deposit": "75.00",
        },
    )
    booking.charge_payment_intent_id = "pi_charge_retry"
    booking.renter_stripe_customer_id = "cus_retry"
    booking.renter_stripe_payment_method_id = "pm_retry"
    booking.save(
        update_fields=[
            "charge_payment_intent_id",
            "renter_stripe_customer_id",
            "renter_stripe_payment_method_id",
        ]
    )

    monkeypatch.setattr("bookings.tasks.timezone.localdate", lambda: today)
    applied: list[dict] = []
    monkeypatch.setattr(
        authorize_deposit_for_start_day,  # type: ignore[arg-type]
        "apply_async",
        lambda args=None, kwargs=None, countdown=None: applied.append(
            {"args": args, "countdown": countdown}
        ),
    )

    def raise_insufficient(*args, **kwargs):
        raise DepositAuthorizationInsufficientFunds("insufficient funds")

    monkeypatch.setattr(
        "bookings.tasks.create_booking_deposit_hold_intent",
        raise_insufficient,
    )
    settings.STRIPE_SECRET_KEY = "sk_test"
    settings.STRIPE_PLATFORM_ACCOUNT_ID = "acct_platform_test"

    refund_calls: list[dict] = []
    transfer_calls: list[dict] = []

    platform_user = get_user_model().objects.create_user(
        username="platform-ledger", password="x", can_list=False, can_rent=False
    )
    settings.PLATFORM_LEDGER_USER_ID = platform_user.id

    monkeypatch.setattr(
        stripe.Refund,
        "create",
        lambda **kwargs: refund_calls.append(kwargs) or SimpleNamespace(id="re_1"),
    )
    monkeypatch.setattr(
        stripe.Transfer,
        "create",
        lambda **kwargs: transfer_calls.append(kwargs) or SimpleNamespace(id="tr_1"),
    )
    monkeypatch.setattr(
        "bookings.domain.ensure_connect_account",
        lambda user: SimpleNamespace(
            stripe_account_id="acct_test_owner",
            payouts_enabled=True,
            charges_enabled=True,
        ),
    )

    first = authorize_deposit_for_start_day(booking.id)
    assert first is False
    booking.refresh_from_db()
    assert booking.deposit_attempt_count == 1
    assert applied == [{"args": [booking.id], "countdown": 3600}]

    second = authorize_deposit_for_start_day(booking.id)
    assert second is False
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.SYSTEM
    assert "Insufficient funds" in (booking.canceled_reason or "")

    assert refund_calls, "refund should be issued"
    refund_kwargs = refund_calls[0]
    assert refund_kwargs["payment_intent"] == "pi_charge_retry"
    assert refund_kwargs["amount"] == 6000  # 50% of 120.00
    assert refund_kwargs["reverse_transfer"] is True
    assert refund_kwargs["refund_application_fee"] is False

    assert transfer_calls, "platform share transfer should be issued"
    transfer_kwargs = transfer_calls[0]
    assert transfer_kwargs["amount"] == 1800  # 20% of 120.00 - owner_fee 6.00
    assert transfer_kwargs["destination"] == "acct_platform_test"
    assert transfer_kwargs["stripe_account"] == "acct_test_owner"

    txn_kinds = set(Transaction.objects.filter(booking=booking).values_list("kind", flat=True))
    assert {
        Transaction.Kind.REFUND,
        Transaction.Kind.OWNER_EARNING,
        Transaction.Kind.PLATFORM_FEE,
    }.issubset(txn_kinds)

    owner_adjustment = Transaction.objects.filter(
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
    ).first()
    assert owner_adjustment is not None
    assert owner_adjustment.amount == Decimal("-78.00")

    platform_txn = Transaction.objects.filter(
        booking=booking,
        kind=Transaction.Kind.PLATFORM_FEE,
    ).first()
    assert platform_txn is not None
    assert platform_txn.amount == Decimal("18.00")


def test_owner_payout_not_sent_on_charge_webhook(monkeypatch, booking_factory, settings):
    today = date.today()
    booking = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.CONFIRMED,
        totals={
            "rental_subtotal": "100.00",
            "service_fee": "10.00",
            "owner_payout": "80.00",
            "platform_fee_total": "10.00",
            "damage_deposit": "50.00",
        },
    )
    booking.save()
    platform_user = get_user_model().objects.create_user(
        username="platform-webhook",
        password="testpass",
        can_list=False,
        can_rent=False,
    )
    settings.PLATFORM_LEDGER_USER_ID = platform_user.id

    event_payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_charge_only",
                "metadata": {"booking_id": str(booking.id), "kind": "booking_charge"},
            }
        },
    }

    def fake_construct(payload, sig_header, secret):
        return event_payload

    monkeypatch.setattr(stripe.Webhook, "construct_event", fake_construct)
    monkeypatch.setattr(
        "payments.stripe_api.create_owner_transfer_for_booking",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("owner transfer should not run")
        ),
    )
    monkeypatch.setattr("payments.stripe_api._get_stripe_api_key", lambda: "sk_test")
    monkeypatch.setattr(
        "payments.stripe_api.stripe.PaymentIntent.retrieve",
        lambda _intent_id, **_kwargs: SimpleNamespace(
            charges=SimpleNamespace(data=[SimpleNamespace(transfer="tr_transfer_123")])
        ),
    )

    factory = APIRequestFactory()
    request = factory.post("/api/payments/stripe/webhook/", data={}, format="json")
    response = stripe_webhook(request)
    assert response.status_code == 200

    owner_txn = Transaction.objects.get(kind=Transaction.Kind.OWNER_EARNING, booking=booking)
    assert owner_txn.amount == Decimal("80.00")
    assert owner_txn.stripe_id == "tr_transfer_123"

    platform_txn = Transaction.objects.get(kind=Transaction.Kind.PLATFORM_FEE, booking=booking)
    assert platform_txn.amount == Decimal("10.00")
