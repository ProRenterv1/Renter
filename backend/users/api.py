from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from notifications import tasks as notification_tasks

from .models import (
    ContactVerificationChallenge,
    LoginEvent,
    PasswordResetChallenge,
    TwoFactorChallenge,
)
from .serializers import (
    ContactVerificationRequestSerializer,
    ContactVerificationVerifySerializer,
    FlexibleTokenObtainPairSerializer,
    PasswordChangeSerializer,
    PasswordResetCompleteSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    ProfileSerializer,
    SignupSerializer,
    TwoFactorLoginResendSerializer,
    TwoFactorLoginVerifySerializer,
    TwoFactorSettingsSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)
TWO_FACTOR_EXPIRY_MINUTES = 10
TWO_FACTOR_RESEND_COOLDOWN = timedelta(seconds=60)


def _mask_contact(contact: str, channel: str) -> str:
    """Return an obfuscated representation of the contact value for UX hints."""
    if channel == TwoFactorChallenge.Channel.EMAIL:
        local, _, domain = contact.partition("@")
        if not local:
            return f"***@{domain}" if domain else "***"
        if len(local) == 1:
            start = local
            end = ""
        else:
            start = local[0]
            end = local[-1]
        masked_local = f"{start}***{end}"
        if domain:
            return f"{masked_local}@{domain}"
        return masked_local

    digits = "".join(ch for ch in contact if ch.isdigit())
    suffix_source = digits or contact
    suffix = suffix_source[-4:] if suffix_source else ""
    return f"****{suffix}"


def _issue_two_factor_challenge(user: User, channel: str, contact: str) -> TwoFactorChallenge:
    """Create a fresh login challenge and dispatch the corresponding notification."""
    now = timezone.now()
    challenge = TwoFactorChallenge(
        user=user,
        channel=channel,
        contact=contact,
        expires_at=now + timedelta(minutes=TWO_FACTOR_EXPIRY_MINUTES),
    )
    raw_code = TwoFactorChallenge.generate_code()
    challenge.set_code(raw_code)
    challenge.save()

    if channel == TwoFactorChallenge.Channel.EMAIL:
        _safe_notify(
            notification_tasks.send_two_factor_code_email,
            user.id,
            contact,
            raw_code,
        )
    else:
        _safe_notify(
            notification_tasks.send_two_factor_code_sms,
            user.id,
            contact,
            raw_code,
        )
    return challenge


def client_ip(request) -> str:
    """
    Return the best-effort client IP using X-Forwarded-For, falling back to REMOTE_ADDR.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        # XFF may be a comma-separated list; take the first non-empty entry.
        for part in forwarded_for.split(","):
            candidate = part.strip()
            if candidate:
                return candidate
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def user_agent(request) -> str:
    """Return the raw user-agent string (may be empty)."""
    return request.META.get("HTTP_USER_AGENT", "")


def audit_login_and_alert(request, user: User) -> LoginEvent:
    """
    Persist login metadata and trigger security notifications when needed.
    """
    ip = client_ip(request)
    ua = user_agent(request)
    ua_hash = hashlib.sha256(ua.encode("utf-8")).hexdigest()

    is_new_device = (
        not user.last_login_ip
        or not user.last_login_ua
        or user.last_login_ip != ip
        or user.last_login_ua != ua
    )

    event = LoginEvent.objects.create(
        user=user,
        ip=ip,
        user_agent=ua,
        ua_hash=ua_hash,
        is_new_device=is_new_device,
    )

    user.last_login = timezone.now()
    user.last_login_ip = ip
    user.last_login_ua = ua
    user.save(update_fields=["last_login", "last_login_ip", "last_login_ua"])

    if is_new_device and user.login_alerts_enabled:
        _safe_notify(notification_tasks.send_login_alert_email, user.id, ip, ua)
        _safe_notify(notification_tasks.send_login_alert_sms, user.id, ip, ua)

    return event


class SignupView(generics.CreateAPIView):
    """Public signup endpoint supporting email or phone."""

    queryset = User.objects.all()
    serializer_class = SignupSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    """Authenticated profile view for the current user."""

    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        self.check_object_permissions(self.request, user)
        return user


class TwoFactorSettingsView(generics.RetrieveUpdateAPIView):
    """Allow authenticated users to manage their 2FA preferences."""

    serializer_class = TwoFactorSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class FlexibleTokenObtainPairView(TokenObtainPairView):
    """Login endpoint that accepts email, phone, or username as the identifier."""

    permission_classes = [permissions.AllowAny]
    serializer_class = FlexibleTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = getattr(serializer, "user", None)
        if user:
            channel, contact = self._select_two_factor_channel(user)
            if channel and contact:
                challenge = _issue_two_factor_challenge(user, channel, contact)
                resend_available_at = challenge.last_sent_at + TWO_FACTOR_RESEND_COOLDOWN
                return Response(
                    {
                        "requires_2fa": True,
                        "challenge_id": challenge.id,
                        "channel": channel,
                        "contact_hint": _mask_contact(contact, channel),
                        "resend_available_at": resend_available_at.isoformat(),
                    },
                    status=status.HTTP_200_OK,
                )

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        if user:
            audit_login_and_alert(request, user)

        return response

    @staticmethod
    def _select_two_factor_channel(user: User) -> tuple[str | None, str | None]:
        if (
            getattr(user, "two_factor_sms_enabled", False)
            and getattr(user, "phone_verified", False)
            and getattr(user, "phone", None)
        ):
            return TwoFactorChallenge.Channel.SMS, user.phone
        if (
            getattr(user, "two_factor_email_enabled", False)
            and getattr(user, "email_verified", False)
            and getattr(user, "email", None)
        ):
            return TwoFactorChallenge.Channel.EMAIL, user.email
        return None, None


class TwoFactorLoginVerifyView(generics.GenericAPIView):
    """Complete a login once the user successfully entered their 2FA code."""

    serializer_class = TwoFactorLoginVerifySerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        challenge = serializer.validated_data["challenge"]

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        challenge.consumed = True
        challenge.save(update_fields=["consumed", "attempts"])

        audit_login_and_alert(request, user)
        return Response(
            {"refresh": str(refresh), "access": str(access)},
            status=status.HTTP_200_OK,
        )


class TwoFactorLoginResendView(generics.GenericAPIView):
    """Allow a user to request that their login code be sent again."""

    serializer_class = TwoFactorLoginResendSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge = serializer.validated_data["challenge"]
        now = timezone.now()
        if challenge.last_sent_at:
            elapsed = now - challenge.last_sent_at
            if elapsed < TWO_FACTOR_RESEND_COOLDOWN:
                remaining = int((TWO_FACTOR_RESEND_COOLDOWN - elapsed).total_seconds())
                raise serializers.ValidationError(
                    {"non_field_errors": [f"Please wait {remaining}s before resending."]}
                )

        raw_code = TwoFactorChallenge.generate_code()
        challenge.expires_at = now + timedelta(minutes=TWO_FACTOR_EXPIRY_MINUTES)
        challenge.set_code(raw_code)
        challenge.save()

        if challenge.channel == TwoFactorChallenge.Channel.EMAIL:
            _safe_notify(
                notification_tasks.send_two_factor_code_email,
                challenge.user_id,
                challenge.contact,
                raw_code,
            )
        else:
            _safe_notify(
                notification_tasks.send_two_factor_code_sms,
                challenge.user_id,
                challenge.contact,
                raw_code,
            )

        resend_available_at = challenge.last_sent_at + TWO_FACTOR_RESEND_COOLDOWN
        return Response(
            {"ok": True, "resend_available_at": resend_available_at.isoformat()},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(generics.GenericAPIView):
    """Initiate a password reset via email or SMS without leaking user existence."""

    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contact = serializer.validated_data["contact"]
        channel = serializer.validated_data["channel"]

        user = (
            User.objects.filter(email__iexact=contact).first()
            if channel == PasswordResetChallenge.Channel.EMAIL
            else User.objects.filter(phone=contact).first()
        )

        challenge_id = None
        if user:
            challenge = self._issue_challenge(user, channel, contact)
            challenge_id = challenge.id

        body = {"ok": True}
        if challenge_id:
            body["challenge_id"] = challenge_id
        return Response(body, status=status.HTTP_200_OK)

    def _issue_challenge(self, user: User, channel: str, contact: str) -> PasswordResetChallenge:
        # Reuse the latest active challenge to avoid spamming rows (simple rate limit).
        challenge = (
            PasswordResetChallenge.objects.filter(
                user=user,
                channel=channel,
                contact=contact,
                consumed=False,
            )
            .order_by("-created_at")
            .first()
        )
        if not challenge or challenge.is_expired():
            challenge = PasswordResetChallenge(
                user=user,
                channel=channel,
                contact=contact,
            )

        raw_code = PasswordResetChallenge.generate_code()
        challenge.expires_at = timezone.now() + timedelta(minutes=15)
        challenge.set_code(raw_code)
        challenge.max_attempts = challenge.max_attempts or 5
        challenge.save()

        if channel == PasswordResetChallenge.Channel.EMAIL:
            _safe_notify(
                notification_tasks.send_password_reset_code_email, user.id, contact, raw_code
            )
        else:
            _safe_notify(
                notification_tasks.send_password_reset_code_sms, user.id, contact, raw_code
            )

        return challenge


class PasswordResetVerifyView(generics.GenericAPIView):
    """Verify that a reset code is valid (challenge_id or contact-based lookup)."""

    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetVerifySerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        challenge = serializer.validated_data["challenge"]
        return Response(
            {"verified": True, "challenge_id": challenge.id},
            status=status.HTTP_200_OK,
        )


class PasswordResetCompleteView(generics.GenericAPIView):
    """Finalize the reset by setting a new password and consuming the challenge."""

    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetCompleteSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        challenge = serializer.validated_data["challenge"]
        new_password = serializer.validated_data["new_password"]

        user.set_password(new_password)
        user.save(update_fields=["password"])

        if user.email:
            _safe_notify(notification_tasks.send_password_changed_email, user.id)
        if getattr(user, "phone", None):
            _safe_notify(notification_tasks.send_password_changed_sms, user.id)

        # Challenge already marked consumed by the serializer, but ensure persistence.
        challenge.consumed = True
        challenge.save(update_fields=["attempts", "consumed"])

        return Response({"ok": True}, status=status.HTTP_200_OK)


class PasswordChangeView(generics.GenericAPIView):
    """Authenticated password change endpoint for users who know their current password."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()
        if user.email:
            _safe_notify(notification_tasks.send_password_changed_email, user.id)
        if getattr(user, "phone", None):
            _safe_notify(notification_tasks.send_password_changed_sms, user.id)

        return Response({"ok": True}, status=status.HTTP_200_OK)


class ContactVerificationRequestView(generics.GenericAPIView):
    """Authenticated endpoint for requesting email or phone verification codes."""

    serializer_class = ContactVerificationRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    resend_cooldown = timedelta(minutes=1)
    expiry_duration = timedelta(minutes=15)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        channel = serializer.validated_data["channel"]
        contact = serializer.validated_data["contact"]

        challenge = self._issue_challenge(user, channel, contact)
        resend_available_at = challenge.last_sent_at + self.resend_cooldown
        return Response(
            {
                "challenge_id": challenge.id,
                "channel": channel,
                "expires_at": challenge.expires_at,
                "resend_available_at": resend_available_at,
            },
            status=status.HTTP_200_OK,
        )

    def _issue_challenge(self, user, channel: str, contact: str) -> ContactVerificationChallenge:
        challenge = (
            ContactVerificationChallenge.objects.filter(
                user=user,
                channel=channel,
                contact=contact,
                consumed=False,
            )
            .order_by("-created_at")
            .first()
        )
        now = timezone.now()
        if challenge and challenge.last_sent_at:
            elapsed = now - challenge.last_sent_at
            if elapsed < self.resend_cooldown:
                remaining = int((self.resend_cooldown - elapsed).total_seconds())
                raise serializers.ValidationError(
                    {"non_field_errors": [f"Please wait {remaining}s before resending."]}
                )

        if not challenge or challenge.is_expired():
            challenge = ContactVerificationChallenge(
                user=user,
                channel=channel,
                contact=contact,
            )

        raw_code = ContactVerificationChallenge.generate_code()
        challenge.expires_at = now + self.expiry_duration
        challenge.max_attempts = challenge.max_attempts or 5
        challenge.set_code(raw_code)
        challenge.save()

        if channel == ContactVerificationChallenge.Channel.EMAIL:
            _safe_notify(
                notification_tasks.send_contact_verification_email,
                user.id,
                contact,
                raw_code,
            )
        else:
            _safe_notify(
                notification_tasks.send_contact_verification_sms,
                user.id,
                contact,
                raw_code,
            )

        return challenge


class ContactVerificationVerifyView(generics.GenericAPIView):
    """Verify a code and update the corresponding user flag."""

    serializer_class = ContactVerificationVerifySerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        channel = serializer.validated_data["channel"]

        if channel == ContactVerificationChallenge.Channel.EMAIL:
            if not user.email_verified:
                user.email_verified = True
                user.save(update_fields=["email_verified"])
        else:
            if not user.phone_verified:
                user.phone_verified = True
                user.save(update_fields=["phone_verified"])

        profile = ProfileSerializer(user, context={"request": request}).data
        return Response(
            {
                "verified": True,
                "channel": channel,
                "profile": profile,
            },
            status=status.HTTP_200_OK,
        )


def _safe_notify(task, *args):
    """Queue Celery tasks without failing the auth flow if the broker is unavailable."""
    try:
        task.delay(*args)
    except Exception:  # pragma: no cover - defensive fallback
        logger.info("notifications task %s could not be queued", task.__name__, exc_info=True)
