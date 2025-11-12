from __future__ import annotations

import re
from typing import Optional, Tuple

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import PasswordResetChallenge

User = get_user_model()
PHONE_CLEAN_RE = re.compile(r"\D+")


def normalize_phone(raw_phone: Optional[str]) -> Optional[str]:
    """
    Return a best-effort E.164 number.

    Numbers containing exactly 10 digits default to +1; everything else must include
    an explicit country code (e.g., +44...).
    """
    if not raw_phone:
        return None

    stripped = raw_phone.strip()
    if not stripped:
        raise serializers.ValidationError("Enter a phone number.")

    digits = PHONE_CLEAN_RE.sub("", stripped)
    if not digits:
        raise serializers.ValidationError("Enter a phone number.")

    if stripped.startswith("+"):
        normalized = f"+{digits}"
    elif len(digits) == 10:
        normalized = f"+1{digits}"
    else:
        raise serializers.ValidationError("Include country code (e.g. +1...).")

    if len(normalized) < 11 or len(normalized) > 17:
        raise serializers.ValidationError("Enter a valid phone number.")
    return normalized


def _normalize_contact(contact: str) -> Tuple[str, str]:
    """Infer whether the contact is email or phone and normalize accordingly."""
    value = (contact or "").strip()
    if not value:
        raise serializers.ValidationError("Enter an email address or phone number.")

    if "@" in value:
        return value.lower(), PasswordResetChallenge.Channel.EMAIL

    normalized_phone = normalize_phone(value)
    if not normalized_phone:
        raise serializers.ValidationError("Enter an email address or phone number.")
    return normalized_phone, PasswordResetChallenge.Channel.SMS


class ProfileSerializer(serializers.ModelSerializer):
    """Read-only profile details with verification flags."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "first_name",
            "last_name",
            "can_rent",
            "can_list",
            "email_verified",
            "phone_verified",
        ]
        read_only_fields = ("id", "email_verified", "phone_verified")


class SignupSerializer(serializers.ModelSerializer):
    """Allow signup via email or phone."""

    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "password",
            "first_name",
            "last_name",
            "can_rent",
            "can_list",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs: dict) -> dict:
        email = (attrs.get("email") or "").strip().lower() or None
        phone = attrs.get("phone")

        if not email and not phone:
            raise serializers.ValidationError(
                {"non_field_errors": ["Provide an email or phone number."]}
            )

        if email:
            attrs["email"] = email
        if phone:
            try:
                attrs["phone"] = normalize_phone(phone)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"phone": exc.detail}) from exc

        if attrs.get("email") and User.objects.filter(email__iexact=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "A user with this email already exists."})
        if attrs.get("phone") and User.objects.filter(phone=attrs["phone"]).exists():
            raise serializers.ValidationError({"phone": "A user with this phone already exists."})

        return attrs

    def create(self, validated_data: dict) -> User:
        password = validated_data.pop("password")
        if not validated_data.get("username"):
            validated_data["username"] = self._generate_username(validated_data)
        user = User.objects.create_user(password=password, **validated_data)
        return user

    def _generate_username(self, data: dict) -> str:
        """Generate a unique username derived from email/phone."""
        source = ""
        if data.get("email"):
            source = data["email"].split("@")[0]
        elif data.get("phone"):
            source = data["phone"].lstrip("+")
        base = re.sub(r"[^a-z0-9]+", "", source.lower()) or "user"
        candidate = base
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            candidate = f"{base}{suffix}"
            suffix += 1
        return candidate


class FlexibleTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Accepts email, phone, or username for authentication and returns a JWT pair.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["identifier"] = serializers.CharField(required=False, allow_blank=True)
        if self.username_field in self.fields:
            self.fields[self.username_field].required = False

    def validate(self, attrs: dict) -> dict:
        identifier = attrs.get("identifier") or attrs.get(self.username_field) or ""
        password = attrs.get("password")
        if not identifier or not password:
            raise serializers.ValidationError(
                {"non_field_errors": ["Provide credentials to log in."]}
            )

        user = self._resolve_user(identifier)
        if not user:
            raise AuthenticationFailed(self.error_messages["no_active_account"])

        # TokenObtainPairSerializer expects the username field in attrs.
        attrs[self.username_field] = user.get_username()
        self.user = user
        return super().validate(attrs)

    def _resolve_user(self, identifier: str) -> Optional[User]:
        value = identifier.strip()
        if not value:
            return None

        if "@" in value:
            user = User.objects.filter(email__iexact=value).first()
            if user:
                return user

        phone_candidate = None
        try:
            phone_candidate = normalize_phone(value)
        except serializers.ValidationError:
            phone_candidate = None
        if phone_candidate:
            user = User.objects.filter(phone=phone_candidate).first()
            if user:
                return user

        return User.objects.filter(username__iexact=value).first()


class PasswordResetRequestSerializer(serializers.Serializer):
    """Request a reset code via email or SMS."""

    contact = serializers.CharField()

    def validate(self, attrs: dict) -> dict:
        contact, channel = _normalize_contact(attrs.get("contact", ""))
        attrs["contact"] = contact
        attrs["channel"] = channel
        return attrs


class _PasswordResetBaseSerializer(serializers.Serializer):
    """Common lookup + code validation logic."""

    challenge_id = serializers.IntegerField(required=False)
    contact = serializers.CharField(required=False, allow_blank=True)
    code = serializers.CharField()

    consume_on_success = False

    default_error_messages = {
        "missing_lookup": "Provide challenge_id or contact.",
        "invalid_code": "Invalid or expired reset code.",
    }

    def validate(self, attrs: dict) -> dict:
        challenge = self._resolve_challenge(attrs)
        self._ensure_challenge_available(challenge)

        match = challenge.check_code(attrs["code"])
        challenge.save(update_fields=["attempts", "consumed"])

        if not match:
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})

        if not self.consume_on_success:
            # Allow the same code to be used later in the completion step.
            challenge.consumed = False
            challenge.save(update_fields=["consumed"])

        attrs["challenge"] = challenge
        attrs["user"] = challenge.user
        return attrs

    def _resolve_challenge(self, attrs: dict) -> Optional[PasswordResetChallenge]:
        challenge_id = attrs.get("challenge_id")
        contact = attrs.get("contact")
        qs = PasswordResetChallenge.objects.select_related("user")

        if challenge_id:
            challenge = qs.filter(id=challenge_id).first()
            if challenge:
                return challenge
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})

        if contact:
            try:
                normalized_contact, channel = _normalize_contact(contact)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"contact": exc.detail}) from exc

            attrs["contact"] = normalized_contact
            attrs["channel"] = channel
            challenge = (
                qs.filter(
                    channel=channel,
                    contact=normalized_contact,
                    consumed=False,
                )
                .order_by("-created_at")
                .first()
            )
            if challenge:
                return challenge
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})

        raise serializers.ValidationError(
            {"non_field_errors": [self.error_messages["missing_lookup"]]}
        )

    def _ensure_challenge_available(self, challenge: PasswordResetChallenge) -> None:
        if not challenge or not challenge.can_attempt():
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})


class PasswordResetVerifySerializer(_PasswordResetBaseSerializer):
    """Verifies that a code is correct without consuming it."""

    consume_on_success = False


class PasswordResetCompleteSerializer(_PasswordResetBaseSerializer):
    """Validate the reset code and new password."""

    new_password = serializers.CharField(write_only=True)
    consume_on_success = True

    def validate_new_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        return attrs
