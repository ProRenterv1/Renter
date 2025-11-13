from datetime import timedelta

import pytest
from django.utils import timezone

from users.models import TwoFactorChallenge
from users.serializers import (
    TwoFactorLoginResendSerializer,
    TwoFactorLoginVerifySerializer,
    TwoFactorSettingsSerializer,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="twofactor",
        email="twofactor@example.com",
        password="Secret123!",
        phone="+15551234567",
    )


def make_challenge(user, *, code: str = "246810", **overrides):
    data = {
        "user": user,
        "channel": TwoFactorChallenge.Channel.EMAIL,
        "contact": user.email,
        "code_hash": TwoFactorChallenge._hash_code(code),
        "expires_at": timezone.now() + timedelta(minutes=5),
    }
    data.update(overrides)
    challenge = TwoFactorChallenge.objects.create(**data)
    challenge.set_code(code)
    challenge.save(update_fields=["code_hash", "attempts", "consumed", "last_sent_at"])
    return challenge, code


def test_two_factor_settings_requires_verified_email(user):
    user.email_verified = False
    user.save(update_fields=["email_verified"])
    serializer = TwoFactorSettingsSerializer(
        instance=user, data={"two_factor_email_enabled": True}, partial=True
    )
    assert serializer.is_valid() is False
    assert serializer.errors["two_factor_email_enabled"][0] == (
        "Verify your email before enabling email 2FA."
    )


def test_two_factor_settings_requires_verified_phone(user):
    user.phone_verified = False
    user.save(update_fields=["phone_verified"])
    serializer = TwoFactorSettingsSerializer(
        instance=user, data={"two_factor_sms_enabled": True}, partial=True
    )
    assert serializer.is_valid() is False
    assert serializer.errors["two_factor_sms_enabled"][0] == (
        "Verify your phone before enabling SMS 2FA."
    )


def test_two_factor_settings_allows_disabling_without_verification(user):
    user.email_verified = False
    user.two_factor_email_enabled = True
    user.save(update_fields=["email_verified", "two_factor_email_enabled"])
    serializer = TwoFactorSettingsSerializer(
        instance=user, data={"two_factor_email_enabled": False}, partial=True
    )
    assert serializer.is_valid(), serializer.errors


def test_two_factor_settings_allows_enabling_when_verified(user):
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    serializer = TwoFactorSettingsSerializer(
        instance=user, data={"two_factor_email_enabled": True}, partial=True
    )
    assert serializer.is_valid(), serializer.errors


def test_two_factor_login_verify_accepts_correct_code(user):
    challenge, code = make_challenge(user, code="123456")
    serializer = TwoFactorLoginVerifySerializer(data={"challenge_id": challenge.id, "code": code})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["user"] == user
    assert serializer.validated_data["challenge"] == challenge
    challenge.refresh_from_db()
    assert challenge.consumed is True
    assert challenge.attempts == 1


def test_two_factor_login_verify_rejects_invalid_code(user):
    challenge, _ = make_challenge(user, code="987654")
    serializer = TwoFactorLoginVerifySerializer(
        data={"challenge_id": challenge.id, "code": "000000"}
    )
    assert serializer.is_valid() is False
    assert serializer.errors["code"][0] == "Invalid or expired verification code."
    challenge.refresh_from_db()
    assert challenge.attempts == 1
    assert challenge.consumed is False


def test_two_factor_login_verify_rejects_expired_challenge(user):
    challenge, code = make_challenge(user, code="555555")
    challenge.expires_at = timezone.now() - timedelta(minutes=1)
    challenge.save(update_fields=["expires_at"])
    serializer = TwoFactorLoginVerifySerializer(data={"challenge_id": challenge.id, "code": code})
    assert serializer.is_valid() is False
    assert serializer.errors["code"][0] == "Invalid or expired verification code."


def test_two_factor_login_verify_rejects_over_attempted_challenge(user):
    challenge, code = make_challenge(user, code="135790")
    challenge.attempts = challenge.max_attempts
    challenge.save(update_fields=["attempts"])
    serializer = TwoFactorLoginVerifySerializer(data={"challenge_id": challenge.id, "code": code})
    assert serializer.is_valid() is False
    assert serializer.errors["code"][0] == "Invalid or expired verification code."


def test_two_factor_login_resend_accepts_valid_challenge(user):
    challenge, _ = make_challenge(user)
    serializer = TwoFactorLoginResendSerializer(data={"challenge_id": challenge.id})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["challenge"] == challenge


@pytest.mark.parametrize(
    "field, value",
    [
        ("expires_at", timezone.now() - timedelta(minutes=1)),
        ("consumed", True),
    ],
)
def test_two_factor_login_resend_rejects_invalid_challenge(user, field, value):
    challenge, _ = make_challenge(user)
    setattr(challenge, field, value)
    challenge.save(update_fields=[field])
    serializer = TwoFactorLoginResendSerializer(data={"challenge_id": challenge.id})
    assert serializer.is_valid() is False
    assert serializer.errors["challenge_id"][0] == "Invalid or expired verification code."
