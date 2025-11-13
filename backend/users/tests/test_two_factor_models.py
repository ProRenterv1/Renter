from datetime import timedelta

import pytest
from django.utils import timezone

from users.models import TwoFactorChallenge

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="twofactor",
        email="twofactor@example.com",
        password="Secret123!",
        phone="+15551234567",
    )


def create_challenge(user, **overrides):
    data = {
        "user": user,
        "channel": TwoFactorChallenge.Channel.EMAIL,
        "contact": user.email,
        "code_hash": TwoFactorChallenge._hash_code("000000"),
        "expires_at": timezone.now() + timedelta(minutes=5),
    }
    data.update(overrides)
    return TwoFactorChallenge.objects.create(**data)


def test_generate_code_returns_six_digits():
    for _ in range(5):
        code = TwoFactorChallenge.generate_code()
        assert len(code) == TwoFactorChallenge.CODE_DIGITS
        assert code.isdigit()


def test_set_code_and_check_code_success(user):
    challenge = create_challenge(user)
    challenge.attempts = 3
    challenge.consumed = True

    raw_code = "654321"
    challenge.set_code(raw_code)

    assert challenge.attempts == 0
    assert challenge.consumed is False
    assert challenge.last_sent_at is not None

    assert challenge.check_code(raw_code) is True
    assert challenge.attempts == 1
    assert challenge.consumed is True


def test_incorrect_code_increments_attempts_until_limit(user):
    challenge = create_challenge(user)
    challenge.set_code("111222")

    for attempt in range(challenge.max_attempts):
        assert challenge.check_code("999999") is False
        assert challenge.attempts == attempt + 1

    assert challenge.can_attempt() is False
    # Further attempts should be blocked and not increase the counter.
    assert challenge.check_code("999999") is False
    assert challenge.attempts == challenge.max_attempts


def test_expiration_disables_additional_attempts(user):
    challenge = create_challenge(user)
    challenge.set_code("123123")

    assert challenge.is_expired() is False
    assert challenge.can_attempt() is True

    challenge.expires_at = timezone.now() - timedelta(seconds=1)
    assert challenge.is_expired() is True
    assert challenge.can_attempt() is False
