from django.contrib.auth import get_user_model
from django.template.loader import render_to_string

User = get_user_model()


def test_email_password_reset_template_includes_code(db):
    user = User.objects.create(username="templater", email="templater@example.com")

    body = render_to_string(
        "email/password_reset_code.txt",
        {"user": user, "code": "123456"},
    )

    assert "templater" in body
    assert "123456" in body


def test_sms_login_alert_template_mentions_ip_and_ua():
    body = render_to_string(
        "sms/login_alert.txt",
        {"ip": "198.51.100.2", "ua": "UnitTest/1.0"},
    )
    assert "198.51.100.2" in body
    assert "UnitTest/1.0" in body
