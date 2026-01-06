import importlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from rest_framework.test import APIClient

import renter.urls as renter_urls
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
    group, _ = Group.objects.get_or_create(name="operator_admin")
    user = User.objects.create_user(
        username="op-admin",
        email="admin@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def target_user():
    return User.objects.create_user(
        username="target", email="target@example.com", password="pass123"
    )


def _client(user):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)
    return client


def test_create_and_list_notes_with_audit(operator_user, target_user):
    client = _client(operator_user)
    payload = {
        "entity_type": "user",
        "entity_id": target_user.id,
        "text": "Investigated account",
        "tags": ["vip", "watch"],
        "reason": "document findings",
    }

    create_resp = client.post("/api/operator/notes/", payload, format="json")
    assert create_resp.status_code == 201, create_resp.data
    note_id = create_resp.data["id"]
    assert set(create_resp.data["tags"]) == {"vip", "watch"}
    assert create_resp.data["entity_type"] == "user"
    assert create_resp.data["entity_id"] == str(target_user.id)
    assert create_resp.data["author"]["id"] == operator_user.id

    list_resp = client.get(
        "/api/operator/notes/",
        {"entity_type": "user", "entity_id": target_user.id},
        format="json",
    )
    assert list_resp.status_code == 200, list_resp.data
    assert len(list_resp.data) == 1
    listed = list_resp.data[0]
    assert listed["id"] == note_id
    assert set(listed["tags"]) == {"vip", "watch"}

    event = OperatorAuditEvent.objects.filter(action="operator.note.create").latest("created_at")
    assert event.entity_type == OperatorAuditEvent.EntityType.OPERATOR_NOTE
    assert event.entity_id == str(note_id)
    assert event.reason == "document findings"
    assert set(event.after_json["tags"]) == {"vip", "watch"}
