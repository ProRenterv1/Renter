"""Tests for chat API read receipts."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from bookings.models import Booking
from chat.models import Conversation, Message

pytestmark = pytest.mark.django_db


def auth(user):
    client = APIClient()
    resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_message_is_not_marked_read_until_other_user_views(
    booking_factory,
    owner_user,
    renter_user,
):
    start = date.today()
    end = start + timedelta(days=1)
    booking = booking_factory(start_date=start, end_date=end, status=Booking.Status.CONFIRMED)
    conversation = Conversation.objects.create(
        booking=booking,
        owner=owner_user,
        renter=renter_user,
    )
    message = Message.objects.create(
        conversation=conversation,
        sender=owner_user,
        text="Is Thursday still good for pickup?",
    )

    owner_client = auth(owner_user)
    initial_resp = owner_client.get(f"/api/chats/{conversation.id}/")
    assert initial_resp.status_code == 200
    last_message = initial_resp.data["messages"][-1]
    assert last_message["id"] == message.id
    assert last_message["is_read"] is False

    renter_client = auth(renter_user)
    renter_resp = renter_client.get(f"/api/chats/{conversation.id}/")
    assert renter_resp.status_code == 200

    follow_up_resp = owner_client.get(f"/api/chats/{conversation.id}/")
    assert follow_up_resp.status_code == 200
    assert follow_up_resp.data["messages"][-1]["is_read"] is True
