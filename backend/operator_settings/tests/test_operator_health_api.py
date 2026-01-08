from __future__ import annotations

import sys
import time
from types import ModuleType

import pytest

from operator_core import tasks as operator_core_tasks

pytestmark = pytest.mark.django_db


class DummyRedis:
    def __init__(self, *, ping_ok: bool = True, last_seen_epoch: float | None = None):
        self._ping_ok = ping_ok
        self._last_seen_epoch = last_seen_epoch if last_seen_epoch is not None else time.time()

    def ping(self):
        return self._ping_ok

    def get(self, key):
        return str(self._last_seen_epoch)

    def setex(self, key, ttl, value):
        return True


def _install_dummy_stripe(monkeypatch, account_id: str = "acct_test"):
    stripe = ModuleType("stripe")
    stripe.api_key = None

    class Account:
        @staticmethod
        def retrieve():
            return {"id": account_id}

    stripe.Account = Account
    monkeypatch.setitem(sys.modules, "stripe", stripe)


def _install_dummy_twilio(monkeypatch):
    twilio = ModuleType("twilio")
    twilio_rest = ModuleType("twilio.rest")

    class Client:
        def __init__(self, sid, token):
            self.sid = sid
            self.token = token

    twilio_rest.Client = Client
    monkeypatch.setitem(sys.modules, "twilio", twilio)
    monkeypatch.setitem(sys.modules, "twilio.rest", twilio_rest)


def _install_dummy_s3_client(monkeypatch):
    class S3Client:
        def list_objects_v2(self, **kwargs):
            return {"ok": True}

    monkeypatch.setattr("storage.s3._client", lambda: S3Client())


def test_operator_health_ok_when_all_checks_ok(operator_support_client, settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test"
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "token"
    settings.USE_S3 = True
    settings.AWS_STORAGE_BUCKET_NAME = "bucket"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"

    from operator_core import health_api as health_api_module

    monkeypatch.setattr(health_api_module, "get_redis_client", lambda: DummyRedis(ping_ok=True))
    _install_dummy_stripe(monkeypatch)
    _install_dummy_twilio(monkeypatch)
    _install_dummy_s3_client(monkeypatch)

    resp = operator_support_client.get("/api/operator/health/")
    assert resp.status_code == 200, resp.data
    assert resp.data["ok"] is True

    checks = resp.data["checks"]
    assert set(checks.keys()) == {"db", "redis", "celery", "stripe", "twilio", "s3", "email"}
    assert checks["redis"]["ok"] is True
    assert checks["celery"]["ok"] is True
    assert checks["stripe"]["ok"] is True
    assert checks["twilio"]["ok"] is True
    assert checks["s3"]["ok"] is True
    assert checks["email"]["ok"] is True


def test_operator_health_returns_503_when_redis_fails(
    operator_support_client, settings, monkeypatch
):
    settings.STRIPE_SECRET_KEY = "sk_test"
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "token"
    settings.USE_S3 = False  # keep skipped
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"

    from operator_core import health_api as health_api_module

    monkeypatch.setattr(health_api_module, "get_redis_client", lambda: DummyRedis(ping_ok=False))
    _install_dummy_stripe(monkeypatch)
    _install_dummy_twilio(monkeypatch)

    resp = operator_support_client.get("/api/operator/health/")
    assert resp.status_code == 503, resp.data
    assert resp.data["ok"] is False
    assert resp.data["checks"]["redis"]["ok"] is False


def test_operator_health_test_email_endpoint_sends(operator_admin_client, settings, monkeypatch):
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"

    calls = []

    def fake_send_mail(subject, body, from_email, recipient_list, fail_silently=False):
        calls.append(
            {
                "subject": subject,
                "body": body,
                "from_email": from_email,
                "recipients": recipient_list,
                "fail_silently": fail_silently,
            }
        )
        return 1

    import django.core.mail

    monkeypatch.setattr(django.core.mail, "send_mail", fake_send_mail)
    resp = operator_admin_client.post(
        "/api/operator/health/test-email/",
        {"to": "to@example.com"},
        format="json",
    )
    assert resp.status_code == 202, resp.data
    assert calls and calls[0]["recipients"] == ["to@example.com"]


def test_operator_health_ping_writes_heartbeat(monkeypatch):
    recorded = {}

    class RedisCapture:
        def setex(self, key, ttl, value):
            recorded["key"] = key
            recorded["ttl"] = ttl
            recorded["value"] = value
            return True

    monkeypatch.setattr(operator_core_tasks, "get_redis_client", lambda: RedisCapture())
    monkeypatch.setattr(operator_core_tasks.time, "time", lambda: 123.45)

    result = operator_core_tasks.operator_health_ping()
    assert result == 123.45
    assert recorded["key"] == operator_core_tasks.CELERY_HEARTBEAT_KEY
    assert recorded["ttl"] == operator_core_tasks.CELERY_HEARTBEAT_TTL_SECONDS
    assert recorded["value"] == "123.45"
