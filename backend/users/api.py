from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from notifications import tasks as notification_tasks

from .models import ContactVerificationChallenge, LoginEvent, PasswordResetChallenge
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
)

User = get_user_model()
logger = logging.getLogger(__name__)


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


class FlexibleTokenObtainPairView(TokenObtainPairView):
    """Login endpoint that accepts email, phone, or username as the identifier."""

    permission_classes = [permissions.AllowAny]
    serializer_class = FlexibleTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        user = getattr(serializer, "user", None)
        if user:
            audit_login_and_alert(request, user)

        return response


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
