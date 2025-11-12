import logging

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from notifications import tasks

User = get_user_model()


@pytest.mark.django_db
def test_password_reset_email_contains_code(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"

    user = User.objects.create_user(
        username="email-user",
        email="email@example.com",
        password="secret123",
    )

    tasks.send_password_reset_code_email.run(user.id, user.email, "654321")

    assert len(mail.outbox) == 1
    assert "654321" in mail.outbox[0].body


@pytest.mark.django_db
def test_sms_task_noop_without_twilio(settings, caplog):
    settings.TWILIO_ACCOUNT_SID = None
    settings.TWILIO_AUTH_TOKEN = None
    settings.TWILIO_FROM_NUMBER = None

    user = User.objects.create_user(
        username="sms-user",
        email="sms@example.com",
        password="secret123",
        phone="+15551234567",
    )

    with caplog.at_level(logging.INFO):
        tasks.send_password_reset_code_sms.run(user.id, user.phone, "999999")

    assert "Twilio config incomplete" in caplog.text
