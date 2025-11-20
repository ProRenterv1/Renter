from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user(
        username="events-user",
        email="events@example.com",
        password="StrongPass123!",
    )


def test_events_stream_requires_authentication(api_client):
    resp = api_client.get("/api/events/stream/")
    assert resp.status_code == 401


def test_events_stream_returns_empty_payload(api_client, user, monkeypatch):
    captured = {}

    def fake_read_user_events(*, user_id, cursor, block_ms, count):
        captured.update(
            {
                "user_id": user_id,
                "cursor": cursor,
                "block_ms": block_ms,
                "count": count,
            }
        )
        return "10-0", []

    monkeypatch.setattr("views_events.read_user_events", fake_read_user_events)
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/events/stream/")

    assert resp.status_code == 200
    assert resp.data["cursor"] == "10-0"
    assert resp.data["events"] == []
    assert resp.data["now"]
    assert captured == {
        "user_id": user.id,
        "cursor": "$",
        "block_ms": 25000,
        "count": 100,
    }


def test_events_stream_returns_events(api_client, user, monkeypatch):
    expected_events = [
        {"id": "1-0", "type": "chat:new_message", "payload": {"foo": "bar"}},
        {"id": "2-0", "type": "booking:status_changed", "payload": {"booking_id": 9}},
    ]

    recorded = {}

    def fake_read_user_events(*, user_id, cursor, block_ms, count):
        recorded.update(
            {
                "user_id": user_id,
                "cursor": cursor,
                "block_ms": block_ms,
                "count": count,
            }
        )
        return "2-0", expected_events

    monkeypatch.setattr("views_events.read_user_events", fake_read_user_events)
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/events/stream/?cursor=0-0&timeout=5")

    assert resp.status_code == 200
    assert resp.data["cursor"] == "2-0"
    assert resp.data["events"] == expected_events
    assert recorded == {
        "user_id": user.id,
        "cursor": "0-0",
        "block_ms": 5000,
        "count": 100,
    }


def test_events_stream_invalid_timeout_uses_default(api_client, user, monkeypatch):
    captured = {}

    def fake_read_user_events(*, user_id, cursor, block_ms, count):
        captured.update(
            {
                "user_id": user_id,
                "cursor": cursor,
                "block_ms": block_ms,
                "count": count,
            }
        )
        return cursor, []

    monkeypatch.setattr("views_events.read_user_events", fake_read_user_events)
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/events/stream/?timeout=abc")

    assert resp.status_code == 200
    assert captured["block_ms"] == 25000
