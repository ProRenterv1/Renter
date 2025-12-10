from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Optional, Tuple

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from identity.models import is_user_identity_verified

from .models import (
    ContactVerificationChallenge,
    LoginEvent,
    PasswordResetChallenge,
    TwoFactorChallenge,
)

User = get_user_model()
PHONE_CLEAN_RE = re.compile(r"\D+")
GENERIC_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\s\.'-]{0,63}$")
PROVINCE_RE = re.compile(r"^[A-Za-z][A-Za-z\s\.'-]{0,63}$")
POSTAL_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s-]{2,15}$")

logger = logging.getLogger(__name__)


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

    avatar = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
    )
    avatar_url = serializers.SerializerMethodField()
    avatar_uploaded = serializers.SerializerMethodField()
    identity_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "first_name",
            "last_name",
            "street_address",
            "city",
            "province",
            "postal_code",
            "birth_date",
            "can_rent",
            "can_list",
            "email_verified",
            "phone_verified",
            "two_factor_email_enabled",
            "two_factor_sms_enabled",
            "avatar_url",
            "avatar_uploaded",
            "avatar",
            "date_joined",
            "stripe_customer_id",
            "identity_verified",
        ]
        read_only_fields = (
            "id",
            "email_verified",
            "phone_verified",
            "two_factor_email_enabled",
            "two_factor_sms_enabled",
            "avatar_url",
            "avatar_uploaded",
            "date_joined",
            "stripe_customer_id",
            "identity_verified",
        )

    @staticmethod
    def _clean_optional_text(value: Optional[str]) -> str:
        return (value or "").strip()

    def validate_phone(self, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        try:
            normalized = normalize_phone(value)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError(exc.detail) from exc

        qs = User.objects.all()
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if normalized and qs.filter(phone=normalized).exists():
            raise serializers.ValidationError("A user with this phone already exists.")
        return normalized

    def validate_street_address(self, value: Optional[str]) -> str:
        return self._clean_optional_text(value)

    def validate_city(self, value: Optional[str]) -> str:
        cleaned = self._clean_optional_text(value)
        if cleaned and not GENERIC_NAME_RE.match(cleaned):
            raise serializers.ValidationError("Enter a valid city name.")
        return cleaned

    def validate_province(self, value: Optional[str]) -> str:
        cleaned = self._clean_optional_text(value).upper()
        if cleaned and not PROVINCE_RE.match(cleaned):
            raise serializers.ValidationError("Enter a valid province or state.")
        return cleaned

    def validate_postal_code(self, value: Optional[str]) -> str:
        cleaned = self._clean_optional_text(value).upper()
        cleaned = cleaned.replace("-", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and not POSTAL_CODE_RE.match(cleaned):
            raise serializers.ValidationError("Enter a valid postal or ZIP code.")
        return cleaned

    def validate_birth_date(self, value):
        if value is None:
            return value
        if value > timezone.localdate():
            raise serializers.ValidationError("Birth date cannot be in the future.")
        return value

    def get_avatar_url(self, obj: User) -> str:
        return obj.avatar_url

    def get_avatar_uploaded(self, obj: User) -> bool:
        return obj.avatar_uploaded

    def get_identity_verified(self, obj: User) -> bool:
        return is_user_identity_verified(obj)

    def update(self, instance: User, validated_data: dict):
        avatar = validated_data.pop("avatar", serializers.empty)
        if avatar is not serializers.empty:
            if avatar:
                if instance.avatar:
                    instance.avatar.delete(save=False)
                instance.avatar = avatar
            else:
                if instance.avatar:
                    instance.avatar.delete(save=False)
                instance.avatar = None

        if "phone" in validated_data:
            new_phone = validated_data.get("phone")
            if new_phone != instance.phone:
                instance.phone_verified = False
        updated = super().update(instance, validated_data)
        # Sync updated personal info to Stripe Connect for owners.
        if updated.can_list:
            try:
                from payments.stripe_api import (
                    StripeConfigurationError,
                    StripePaymentError,
                    StripeTransientError,
                    sync_connect_account_personal_info,
                )

                sync_connect_account_personal_info(updated)
            except (StripeConfigurationError, StripeTransientError, StripePaymentError) as exc:
                logger.warning(
                    "connect_sync_profile_failed",
                    exc_info=True,
                    extra={"user_id": updated.id, "error": str(exc)},
                )
        return updated


class PublicProfileSerializer(serializers.ModelSerializer):
    """Limited profile details that are safe to expose publicly."""

    avatar_url = serializers.SerializerMethodField()
    avatar_uploaded = serializers.SerializerMethodField()
    identity_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "city",
            "avatar_url",
            "avatar_uploaded",
            "date_joined",
            "identity_verified",
            "rating",
            "review_count",
        ]
        read_only_fields = tuple(fields)

    def get_avatar_url(self, obj: User) -> str:
        return obj.avatar_url

    def get_avatar_uploaded(self, obj: User) -> bool:
        return obj.avatar_uploaded

    def get_identity_verified(self, obj: User) -> bool:
        return is_user_identity_verified(obj)


class LoginEventSerializer(serializers.ModelSerializer):
    """Expose login events with UX-friendly fields."""

    device = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()

    class Meta:
        model = LoginEvent
        fields = ("id", "device", "ip", "date", "is_new_device")

    def get_device(self, obj: LoginEvent) -> str:
        ua = (obj.user_agent or "").lower()
        if "chrome" in ua and "windows" in ua:
            return "Chrome on Windows"
        if "chrome" in ua and "mac" in ua:
            return "Chrome on Mac"
        if "chrome" in ua and "android" in ua:
            return "Chrome on Android"
        if "safari" in ua and "iphone" in ua:
            return "Safari on iPhone"
        if "safari" in ua and "mac" in ua:
            return "Safari on Mac"
        if "firefox" in ua and "mac" in ua:
            return "Firefox on Mac"
        if "firefox" in ua and "windows" in ua:
            return "Firefox on Windows"
        if "edge" in ua and "windows" in ua:
            return "Edge on Windows"
        return "Unknown device"

    def get_date(self, obj: LoginEvent) -> str:
        dt = timezone.localtime(obj.created_at)
        event_date = dt.date()
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        time_str = dt.strftime("%I:%M %p").lstrip("0")
        if event_date == today:
            return f"Today at {time_str}"
        if event_date == yesterday:
            return f"Yesterday at {time_str}"

        month = dt.strftime("%b")
        date_str = f"{month} {event_date.day}, {event_date.year}"
        return f"{date_str} at {time_str}"


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
        if user.can_list:
            from payments.stripe_api import (
                StripeConfigurationError,
                StripePaymentError,
                StripeTransientError,
                ensure_connect_account,
            )

            try:
                ensure_connect_account(user)
            except (StripeConfigurationError, StripeTransientError, StripePaymentError) as exc:
                logger.warning(
                    "Stripe Connect account creation skipped during signup for user %s: %s",
                    user.id,
                    exc,
                )
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


class PasswordChangeSerializer(serializers.Serializer):
    """Allow authenticated users to update their password."""

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    default_error_messages = {
        "incorrect_current": "Current password is incorrect.",
        "password_unmodified": "New password must be different from the current password.",
    }

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(self.error_messages["incorrect_current"])
        return value

    def validate_new_password(self, value: str) -> str:
        user = self.context["request"].user
        validate_password(value, user)
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": self.error_messages["password_unmodified"]}
            )
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return user


class ContactVerificationRequestSerializer(serializers.Serializer):
    """Request a verification code for the user's email or phone."""

    channel = serializers.ChoiceField(choices=ContactVerificationChallenge.Channel.choices)

    default_error_messages = {
        "missing_email": "Add an email address before requesting verification.",
        "missing_phone": "Add a phone number before requesting verification.",
    }

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        channel = attrs["channel"]
        if channel == ContactVerificationChallenge.Channel.EMAIL:
            contact = (user.email or "").strip().lower()
            if not contact:
                raise serializers.ValidationError(
                    {"channel": [self.error_messages["missing_email"]]}
                )
        else:
            contact = user.phone
            if not contact:
                raise serializers.ValidationError(
                    {"channel": [self.error_messages["missing_phone"]]}
                )
        attrs["contact"] = contact
        attrs["user"] = user
        return attrs


class ContactVerificationVerifySerializer(serializers.Serializer):
    """Verify a previously delivered contact verification code."""

    channel = serializers.ChoiceField(choices=ContactVerificationChallenge.Channel.choices)
    code = serializers.CharField()
    challenge_id = serializers.IntegerField(required=False)

    default_error_messages = {
        "invalid_code": "Invalid or expired verification code.",
        "missing_contact": "Add contact information before verifying.",
        "contact_mismatch": "Your contact information changed. Request a new code.",
    }

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        channel = attrs["channel"]
        challenge = self._resolve_challenge(user, channel, attrs.get("challenge_id"))
        if not challenge or not challenge.can_attempt():
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})

        code = attrs["code"]
        match = challenge.check_code(code)
        challenge.save(update_fields=["attempts", "consumed"])
        if not match:
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})

        current_contact = self._current_contact(user, channel)
        if not current_contact:
            raise serializers.ValidationError({"channel": [self.error_messages["missing_contact"]]})
        if challenge.contact != current_contact:
            raise serializers.ValidationError(
                {"non_field_errors": [self.error_messages["contact_mismatch"]]}
            )

        attrs["challenge"] = challenge
        attrs["user"] = user
        return attrs

    @staticmethod
    def _current_contact(user, channel: str) -> Optional[str]:
        if channel == ContactVerificationChallenge.Channel.EMAIL:
            return (user.email or "").strip().lower()
        return user.phone

    @staticmethod
    def _resolve_challenge(
        user, channel: str, challenge_id: Optional[int]
    ) -> Optional[ContactVerificationChallenge]:
        qs = ContactVerificationChallenge.objects.filter(
            user=user,
            channel=channel,
            consumed=False,
        )
        if challenge_id:
            return qs.filter(id=challenge_id).first()
        return qs.order_by("-created_at").first()


class TwoFactorSettingsSerializer(serializers.ModelSerializer):
    """Enable/disable 2FA channels with verification guards."""

    class Meta:
        model = User
        fields = [
            "two_factor_email_enabled",
            "two_factor_sms_enabled",
            "email_verified",
            "phone_verified",
        ]
        read_only_fields = ("email_verified", "phone_verified")

    def validate(self, attrs: dict) -> dict:
        request = self.context.get("request")
        user = self.instance or getattr(request, "user", None)
        if not user:
            return attrs

        def final_value(field: str) -> bool:
            if field in attrs:
                return attrs[field]
            return getattr(user, field)

        if final_value("two_factor_email_enabled") and not user.email_verified:
            raise serializers.ValidationError(
                {"two_factor_email_enabled": "Verify your email before enabling email 2FA."}
            )

        if final_value("two_factor_sms_enabled") and not user.phone_verified:
            raise serializers.ValidationError(
                {"two_factor_sms_enabled": "Verify your phone before enabling SMS 2FA."}
            )
        return attrs


class TwoFactorLoginVerifySerializer(serializers.Serializer):
    """Verify a submitted login 2FA code."""

    challenge_id = serializers.IntegerField()
    code = serializers.CharField()

    default_error_messages = {
        "invalid_code": "Invalid or expired verification code.",
    }

    def validate(self, attrs: dict) -> dict:
        challenge = self._get_challenge(attrs["challenge_id"])
        if (
            not challenge
            or challenge.is_expired()
            or challenge.consumed
            or not challenge.can_attempt()
        ):
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})

        if not challenge.check_code(attrs["code"]):
            challenge.save(update_fields=["attempts", "consumed"])
            raise serializers.ValidationError({"code": self.error_messages["invalid_code"]})

        challenge.save(update_fields=["attempts", "consumed"])
        attrs["challenge"] = challenge
        attrs["user"] = challenge.user
        return attrs

    @staticmethod
    def _get_challenge(challenge_id: int) -> Optional[TwoFactorChallenge]:
        try:
            return TwoFactorChallenge.objects.select_related("user").get(pk=challenge_id)
        except TwoFactorChallenge.DoesNotExist:
            return None


class TwoFactorLoginResendSerializer(serializers.Serializer):
    """Validate a resend request before the view re-delivers the code."""

    challenge_id = serializers.IntegerField()

    default_error_messages = {
        "invalid_challenge": "Invalid or expired verification code.",
    }

    def validate(self, attrs: dict) -> dict:
        challenge = self._get_challenge(attrs["challenge_id"])
        if not challenge or challenge.is_expired() or challenge.consumed:
            raise serializers.ValidationError(
                {"challenge_id": self.error_messages["invalid_challenge"]}
            )
        attrs["challenge"] = challenge
        return attrs

    @staticmethod
    def _get_challenge(challenge_id: int) -> Optional[TwoFactorChallenge]:
        try:
            return TwoFactorChallenge.objects.select_related("user").get(pk=challenge_id)
        except TwoFactorChallenge.DoesNotExist:
            return None
