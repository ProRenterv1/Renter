import importlib
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

import renter.urls as renter_urls
from bookings.models import Booking
from disputes.models import DisputeCase
from listings.services import compute_booking_totals
from notifications import tasks as notification_tasks
from notifications.models import NotificationLog
from operator_bookings.models import BookingEvent
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


def test_operator_bookings_requires_operator(listing, owner_user, renter_user):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    client = _ops_client()
    resp = client.get("/api/operator/bookings/")
    assert resp.status_code in (401, 403)
    assert booking is not None


def test_operator_bookings_filters(operator_user, listing, owner_user, renter_user, other_user):
    now = timezone.now()
    old = now - timedelta(days=2)
    booking_recent = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
        status=Booking.Status.PAID,
        return_confirmed_at=None,
    )
    Booking.objects.filter(pk=booking_recent.id).update(created_at=now)
    booking_old = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=other_user,
        start_date=timezone.localdate() - timedelta(days=3),
        end_date=timezone.localdate() - timedelta(days=1),
        status=Booking.Status.CONFIRMED,
    )
    Booking.objects.filter(pk=booking_old.id).update(created_at=old)

    overdue_booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate() - timedelta(days=5),
        end_date=timezone.localdate() - timedelta(days=2),
        status=Booking.Status.PAID,
        return_confirmed_at=None,
    )

    client = _ops_client(operator_user)
    resp = client.get(
        "/api/operator/bookings/",
        {
            "status": "paid",
            "owner": owner_user.id,
            "renter": renter_user.id,
            "created_at_after": (now - timedelta(hours=1)).isoformat(),
            "created_at_before": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert resp.status_code == 200, resp.data
    payload = _results(resp)
    assert len(payload) == 1
    assert payload[0]["id"] == booking_recent.id

    resp_overdue = client.get("/api/operator/bookings/", {"overdue": True})
    payload_overdue = _results(resp_overdue)
    assert resp_overdue.status_code == 200
    assert overdue_booking.id in [b["id"] for b in payload_overdue]
    assert booking_recent.id not in [b["id"] for b in payload_overdue]


def test_operator_booking_detail_includes_events_and_disputes(
    operator_user, listing, owner_user, renter_user
):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    earlier = timezone.now() - timedelta(hours=1)
    event1 = BookingEvent.objects.create(
        booking=booking,
        type=BookingEvent.Type.STATUS_CHANGE,
        payload={"from": "paid", "to": "completed"},
    )
    BookingEvent.objects.filter(pk=event1.id).update(created_at=earlier)
    event2 = BookingEvent.objects.create(
        booking=booking, type=BookingEvent.Type.OPERATOR_ACTION, payload={"note": "checked"}
    )
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        description="desc",
        status=DisputeCase.Status.OPEN,
    )

    client = _ops_client(operator_user)
    resp = client.get(f"/api/operator/bookings/{booking.id}/")

    assert resp.status_code == 200, resp.data
    events = resp.data["events"]
    assert [e["id"] for e in events] == [event2.id, event1.id]
    disputes = resp.data["disputes"]
    assert disputes[0]["id"] == dispute.id
    assert disputes[0]["status"] == dispute.status


def test_force_cancel_records_audit_and_event(operator_user, listing, owner_user, renter_user):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
        status=Booking.Status.CONFIRMED,
    )

    client = _ops_client(operator_user)
    resp = client.post(
        f"/api/operator/bookings/{booking.id}/force-cancel/",
        {"actor": "owner", "reason": "duplicate booking"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.OWNER

    audit_event = OperatorAuditEvent.objects.filter(action="operator.booking.force_cancel").latest(
        "created_at"
    )
    assert audit_event.entity_id == str(booking.id)
    assert audit_event.reason == "duplicate booking"

    op_event = BookingEvent.objects.filter(
        booking=booking, type=BookingEvent.Type.OPERATOR_ACTION
    ).latest("created_at")
    assert op_event.actor_id == operator_user.id
    assert op_event.payload["action"] == "force_cancel"


def test_force_complete_sets_return_and_audit(operator_user, listing, owner_user, renter_user):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
    )
    client = _ops_client(operator_user)
    resp = client.post(
        f"/api/operator/bookings/{booking.id}/force-complete/",
        {"reason": "manual close"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED
    assert booking.return_confirmed_at is not None
    assert booking.dispute_window_expires_at is not None

    audit_event = OperatorAuditEvent.objects.filter(
        action="operator.booking.force_complete"
    ).latest("created_at")
    assert audit_event.reason == "manual close"
    assert audit_event.entity_id == str(booking.id)

    op_event = BookingEvent.objects.filter(
        booking=booking, type=BookingEvent.Type.OPERATOR_ACTION
    ).latest("created_at")
    assert op_event.payload["action"] == "force_complete"


def test_adjust_dates_updates_totals(operator_user, listing, owner_user, renter_user):
    start = timezone.localdate()
    end = start + timedelta(days=2)
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=start,
        end_date=end,
        status=Booking.Status.CONFIRMED,
        totals={},
    )
    new_start = start + timedelta(days=5)
    new_end = new_start + timedelta(days=3)

    client = _ops_client(operator_user)
    resp = client.post(
        f"/api/operator/bookings/{booking.id}/adjust-dates/",
        {"start_date": new_start.isoformat(), "end_date": new_end.isoformat(), "reason": "shift"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.start_date == new_start
    assert booking.end_date == new_end
    assert booking.totals == compute_booking_totals(
        listing=listing, start_date=new_start, end_date=new_end
    )

    audit_event = OperatorAuditEvent.objects.filter(action="operator.booking.adjust_dates").latest(
        "created_at"
    )
    assert audit_event.reason == "shift"
    assert audit_event.after_json["start_date"] == new_start.isoformat()

    op_event = BookingEvent.objects.filter(
        booking=booking, type=BookingEvent.Type.OPERATOR_ACTION
    ).latest("created_at")
    assert op_event.payload["action"] == "adjust_dates"


def test_resend_notifications_handles_failures(
    monkeypatch, operator_user, listing, owner_user, renter_user
):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
    )

    calls: list[str] = []

    def _make_stub(label: str, raises: bool = False):
        def _stub(*args, **kwargs):
            calls.append(label)
            if raises:
                raise RuntimeError("fail")

        return _stub

    monkeypatch.setattr(
        notification_tasks.send_booking_request_email, "delay", _make_stub("booking_request")
    )
    monkeypatch.setattr(
        notification_tasks.send_booking_status_email, "delay", _make_stub("status_update")
    )
    monkeypatch.setattr(
        notification_tasks.send_booking_payment_receipt_email,
        "delay",
        _make_stub("receipt", raises=True),
    )
    monkeypatch.setattr(
        notification_tasks.send_booking_completed_email, "delay", _make_stub("completed")
    )

    client = _ops_client(operator_user)
    resp = client.post(
        f"/api/operator/bookings/{booking.id}/resend-notifications/",
        {
            "types": ["booking_request", "status_update", "receipt", "completed", "status_update"],
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_207_MULTI_STATUS, resp.data
    assert resp.data["queued"] == ["booking_request", "status_update", "completed"]
    assert resp.data["failed"] == ["receipt"]
    assert calls.count("status_update") == 1

    audit_event = OperatorAuditEvent.objects.filter(
        action="operator.booking.resend_notifications"
    ).latest("created_at")
    assert audit_event.entity_id == str(booking.id)
    assert audit_event.after_json["queued"] == ["booking_request", "status_update", "completed"]
    assert audit_event.after_json["failed"] == ["receipt"]

    op_event = BookingEvent.objects.filter(
        booking=booking, type=BookingEvent.Type.OPERATOR_ACTION
    ).latest("created_at")
    assert op_event.payload["action"] == "resend_notifications"
    assert op_event.payload["failed"] == ["receipt"]


@pytest.mark.parametrize("status_value", [Booking.Status.CONFIRMED, Booking.Status.PAID])
def test_force_cancel_multiple_statuses(
    operator_user, listing, owner_user, renter_user, status_value
):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=3),
        status=status_value,
    )
    client = _ops_client(operator_user)
    resp = client.post(
        f"/api/operator/bookings/{booking.id}/force-cancel/",
        {"actor": "owner", "reason": "policy"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELED
    assert OperatorAuditEvent.objects.filter(
        action="operator.booking.force_cancel", entity_id=str(booking.id)
    ).exists()
    assert BookingEvent.objects.filter(
        booking=booking, type=BookingEvent.Type.OPERATOR_ACTION, payload__action="force_cancel"
    ).exists()


def test_force_complete_idempotent(operator_user, listing, owner_user, renter_user):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
    )
    client = _ops_client(operator_user)
    first = client.post(
        f"/api/operator/bookings/{booking.id}/force-complete/", {"reason": "manual"}
    )
    assert first.status_code == 200, first.data
    second = client.post(f"/api/operator/bookings/{booking.id}/force-complete/")
    assert second.status_code == 200, second.data
    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED
    assert (
        OperatorAuditEvent.objects.filter(
            action="operator.booking.force_complete", entity_id=str(booking.id)
        ).count()
        >= 1
    )


def test_adjust_dates_validation_and_conflict(
    operator_user, listing, owner_user, renter_user, other_user
):
    start = timezone.localdate()
    end = start + timedelta(days=3)
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=start,
        end_date=end,
        status=Booking.Status.CONFIRMED,
        totals={},
    )
    Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=other_user,
        start_date=start + timedelta(days=1),
        end_date=end + timedelta(days=1),
        status=Booking.Status.CONFIRMED,
    )
    client = _ops_client(operator_user)
    invalid = client.post(
        f"/api/operator/bookings/{booking.id}/adjust-dates/",
        {"start_date": end.isoformat(), "end_date": start.isoformat()},
        format="json",
    )
    assert invalid.status_code == status.HTTP_400_BAD_REQUEST

    conflict = client.post(
        f"/api/operator/bookings/{booking.id}/adjust-dates/",
        {
            "start_date": (start + timedelta(days=1)).isoformat(),
            "end_date": (end + timedelta(days=1)).isoformat(),
        },
        format="json",
    )
    assert conflict.status_code == status.HTTP_400_BAD_REQUEST


def test_resend_notifications_creates_notification_logs(
    monkeypatch, operator_user, listing, owner_user, renter_user
):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=2),
        status=Booking.Status.PAID,
    )

    def _success(*args, **kwargs):
        NotificationLog.objects.create(
            channel=NotificationLog.Channel.EMAIL,
            type="booking_request",
            status=NotificationLog.Status.SENT,
            booking_id=booking.id,
        )

    def _fail(*args, **kwargs):
        NotificationLog.objects.create(
            channel=NotificationLog.Channel.EMAIL,
            type="receipt",
            status=NotificationLog.Status.FAILED,
            booking_id=booking.id,
            error="boom",
        )
        raise RuntimeError("boom")

    monkeypatch.setattr(notification_tasks.send_booking_request_email, "delay", _success)
    monkeypatch.setattr(notification_tasks.send_booking_payment_receipt_email, "delay", _fail)

    client = _ops_client(operator_user)
    resp = client.post(
        f"/api/operator/bookings/{booking.id}/resend-notifications/",
        {"types": ["booking_request", "receipt"]},
        format="json",
    )
    assert resp.status_code == status.HTTP_207_MULTI_STATUS
    logs = NotificationLog.objects.filter(booking_id=booking.id)
    assert logs.filter(type="booking_request", status=NotificationLog.Status.SENT).exists()
    assert logs.filter(type="receipt", status=NotificationLog.Status.FAILED).exists()
