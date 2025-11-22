"""Tests for BookingViewSet permissions and payment/cancel flows."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from bookings import api as bookings_api
from bookings.models import Booking
from listings.models import Listing
from payments_cancellation_policy import CancellationSettlement

pytestmark = pytest.mark.django_db

User = get_user_model()


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


def booking_payload(listing, start, end):
    return {
        "listing": listing.id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


def test_booking_endpoints_require_authentication(listing):
    client = APIClient()
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)

    list_resp = client.get("/api/bookings/")
    assert list_resp.status_code == 401

    create_resp = client.post(
        "/api/bookings/",
        booking_payload(listing, start, end),
        format="json",
    )
    assert create_resp.status_code == 401

    detail_resp = client.get("/api/bookings/1/")
    assert detail_resp.status_code == 401


def make_listing(owner):
    return Listing.objects.create(
        owner=owner,
        title="Owner Listing",
        description="Owned by renter",
        daily_price_cad=Decimal("30.00"),
        replacement_value_cad=Decimal("500.00"),
        damage_deposit_cad=Decimal("150.00"),
        city="Edmonton",
        is_active=True,
        is_available=True,
    )


def test_booking_detail_access_limited_to_participants(
    booking_factory,
    owner_user,
    renter_user,
    other_user,
):
    start = date.today() + timedelta(days=3)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
    )

    owner_client = _auth_client(owner_user)
    renter_client = _auth_client(renter_user)
    stranger_client = _auth_client(other_user)

    owner_resp = owner_client.get(f"/api/bookings/{booking.id}/")
    renter_resp = renter_client.get(f"/api/bookings/{booking.id}/")
    stranger_resp = stranger_client.get(f"/api/bookings/{booking.id}/")

    assert owner_resp.status_code == 200, owner_resp.data
    assert renter_resp.status_code == 200, renter_resp.data
    assert stranger_resp.status_code in {403, 404}


@pytest.mark.parametrize(
    ("can_rent", "email_verified", "phone_verified", "message"),
    [
        (False, True, True, "Your account is not allowed to rent items."),
        (
            True,
            False,
            True,
            "Please verify both your email and phone number before renting tools.",
        ),
        (
            True,
            True,
            False,
            "Please verify both your email and phone number before renting tools.",
        ),
    ],
)
def test_booking_create_requires_rent_permissions(
    listing,
    can_rent,
    email_verified,
    phone_verified,
    message,
):
    user = User.objects.create_user(
        username=f"renter-{int(can_rent)}-{int(email_verified)}-{int(phone_verified)}",
        password="testpass",
        can_list=False,
        can_rent=can_rent,
        email_verified=email_verified,
        phone_verified=phone_verified,
    )
    client = _auth_client(user)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=3)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == message


def test_booking_create_happy_path_sets_renter(listing, other_user):
    client = _auth_client(other_user)
    start = date.today() + timedelta(days=4)
    end = start + timedelta(days=2)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 201, resp.data
    booking = Booking.objects.get(pk=resp.data["id"])
    assert booking.renter_id == other_user.id
    assert booking.owner_id == listing.owner_id


def test_cannot_book_own_listing():
    user = User.objects.create_user(
        username="self-renter",
        password="testpass",
        can_list=True,
        can_rent=True,
        email_verified=True,
        phone_verified=True,
    )
    listing = make_listing(user)
    client = _auth_client(user)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert resp.data["listing"][0] == "You cannot create bookings for your own listing."


def test_pay_booking_renter_only_and_status_transition(
    booking_factory,
    owner_user,
    renter_user,
    other_user,
    monkeypatch,
):
    start = date.today() + timedelta(days=6)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
    )

    ensure_calls: list[tuple[int, str | None]] = []
    payment_calls: list[tuple[int, str, str]] = []

    def fake_ensure(user, customer_id=None):
        ensure_calls.append((user.id, customer_id))
        return customer_id or "cus_generated"

    def fake_create(*, booking, customer_id, payment_method_id):
        payment_calls.append((booking.id, customer_id, payment_method_id))
        return "pi_charge_pay", "pi_deposit_pay"

    monkeypatch.setattr(bookings_api, "ensure_stripe_customer", fake_ensure)
    monkeypatch.setattr(bookings_api, "create_booking_payment_intents", fake_create)

    receipt_calls: list[tuple[int, int]] = []
    from notifications import tasks as notification_tasks

    monkeypatch.setattr(
        notification_tasks.send_booking_payment_receipt_email,
        "delay",
        lambda renter_id, booking_id: receipt_calls.append((renter_id, booking_id)),
    )

    owner_client = _auth_client(owner_user)
    owner_resp = owner_client.post(
        f"/api/bookings/{booking.id}/pay/",
        {"stripe_payment_method_id": "pm_owner"},
        format="json",
    )
    assert owner_resp.status_code == 403

    stranger_client = _auth_client(other_user)
    stranger_resp = stranger_client.post(
        f"/api/bookings/{booking.id}/pay/",
        {"stripe_payment_method_id": "pm_stranger"},
        format="json",
    )
    assert stranger_resp.status_code in {403, 404}

    renter_client = _auth_client(renter_user)
    renter_resp = renter_client.post(
        f"/api/bookings/{booking.id}/pay/",
        {
            "stripe_payment_method_id": "pm_pay",
            "stripe_customer_id": "cus_client",
        },
        format="json",
    )

    assert renter_resp.status_code == 200, renter_resp.data
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PAID
    assert booking.charge_payment_intent_id == "pi_charge_pay"
    assert booking.deposit_hold_id == "pi_deposit_pay"
    assert ensure_calls == [(renter_user.id, "cus_client")]
    assert payment_calls == [(booking.id, "cus_client", "pm_pay")]
    assert receipt_calls == [(renter_user.id, booking.id)]


def test_pay_requires_confirmed_status(booking_factory, renter_user):
    start = date.today() + timedelta(days=2)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )
    client = _auth_client(renter_user)

    resp = client.post(
        f"/api/bookings/{booking.id}/pay/",
        {"stripe_payment_method_id": "pm_not_confirmed"},
        format="json",
    )

    assert resp.status_code == 400
    assert resp.data["detail"] == "Booking is not in a payable state."


def test_cancel_requires_participant(booking_factory, owner_user, renter_user, other_user):
    start = date.today() + timedelta(days=5)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
    )

    stranger_client = _auth_client(other_user)
    stranger_resp = stranger_client.post(f"/api/bookings/{booking.id}/cancel/")
    assert stranger_resp.status_code == 403

    owner_client = _auth_client(owner_user)
    owner_resp = owner_client.post(f"/api/bookings/{booking.id}/cancel/")
    assert owner_resp.status_code == 200

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.OWNER

    new_start = start + timedelta(days=5)
    renter_booking = booking_factory(
        start_date=new_start,
        end_date=new_start + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
    )
    renter_client = _auth_client(renter_user)
    renter_resp = renter_client.post(f"/api/bookings/{renter_booking.id}/cancel/")
    assert renter_resp.status_code == 200
    renter_booking.refresh_from_db()
    assert renter_booking.status == Booking.Status.CANCELED
    assert renter_booking.canceled_by == Booking.CanceledBy.RENTER


def test_cancel_pre_payment_skips_settlement(monkeypatch, booking_factory, renter_user):
    start = date.today() + timedelta(days=7)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=3),
        status=Booking.Status.CONFIRMED,
    )
    booking.charge_payment_intent_id = ""
    booking.save(update_fields=["charge_payment_intent_id", "status"])

    def fail_compute(**kwargs):
        raise AssertionError("compute_refund_amounts should not be called for pre-payment cancel")

    def fail_apply(*args, **kwargs):
        raise AssertionError(
            "apply_cancellation_settlement should not be called for pre-payment cancel"
        )

    monkeypatch.setattr(bookings_api, "compute_refund_amounts", fail_compute)
    monkeypatch.setattr(bookings_api, "apply_cancellation_settlement", fail_apply)

    client = _auth_client(renter_user)
    resp = client.post(
        f"/api/bookings/{booking.id}/cancel/",
        {"reason": "Plans changed"},
        format="json",
    )

    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.RENTER
    assert booking.auto_canceled is False


def test_cancel_post_payment_invokes_settlement(
    monkeypatch,
    booking_factory,
    owner_user,
    renter_user,
):
    start = date.today() + timedelta(days=9)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
    )
    booking.charge_payment_intent_id = "pi_paid_123"
    booking.deposit_hold_id = "pi_deposit_123"
    booking.totals = {
        "rental_subtotal": "120.00",
        "renter_fee": "10.00",
        "damage_deposit": "50.00",
    }
    booking.save(update_fields=["charge_payment_intent_id", "deposit_hold_id", "totals", "status"])

    settlement = CancellationSettlement(
        refund_to_renter=Decimal("25.00"),
        owner_delta=Decimal("-10.00"),
        platform_delta=Decimal("-5.00"),
        deposit_capture_amount=Decimal("0.00"),
        deposit_release_amount=Decimal("50.00"),
    )

    calls = {"compute": 0, "apply": []}

    def fake_compute(*, booking, actor, today):
        calls["compute"] += 1
        return settlement

    def fake_apply(booking_obj, settlement_obj):
        calls["apply"].append((booking_obj.id, settlement_obj))

    monkeypatch.setattr(bookings_api, "compute_refund_amounts", fake_compute)
    monkeypatch.setattr(bookings_api, "apply_cancellation_settlement", fake_apply)

    from notifications import tasks as notification_tasks

    monkeypatch.setattr(
        notification_tasks.send_booking_status_email, "delay", lambda *args, **kwargs: None
    )

    owner_client = _auth_client(owner_user)
    resp = owner_client.post(
        f"/api/bookings/{booking.id}/cancel/",
        {"reason": "Owner cannot fulfill"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.OWNER
    assert calls["compute"] == 1
    assert calls["apply"] == [(booking.id, settlement)]
