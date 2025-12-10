from __future__ import annotations

import hashlib
import secrets
from urllib.parse import quote_plus

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Primary user object augmented with security metadata."""

    phone = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        help_text="Optional E.164 formatted phone number.",
    )
    street_address = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional street address for rentals.",
    )
    city = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="City for the primary address.",
    )
    province = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Province or state for the primary address.",
    )
    postal_code = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Postal or ZIP code for the primary address.",
    )
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_ua = models.TextField(null=True, blank=True)
    login_alerts_enabled = models.BooleanField(default=True)
    two_factor_email_enabled = models.BooleanField(default=False)
    two_factor_sms_enabled = models.BooleanField(default=False)

    can_rent = models.BooleanField(default=True)
    can_list = models.BooleanField(default=True)
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        help_text="Optional profile photo shown to other users.",
    )
    stripe_customer_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Stripe Customer ID for renter payments.",
    )
    rating = models.FloatField(null=True, blank=True)
    review_count = models.PositiveIntegerField(default=0)
    birth_date = models.DateField(null=True, blank=True, help_text="Optional birth date for KYC.")

    def is_owner(self) -> bool:
        return bool(self.can_list)

    def is_renter(self) -> bool:
        return bool(self.can_rent)

    def _avatar_placeholder_seed(self) -> str:
        base_seed = (self.get_full_name() or self.username or f"user-{self.pk or 'anon'}").strip()
        if not base_seed:
            base_seed = f"user-{self.pk or 'anon'}"
        return base_seed

    def _build_media_url(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        base_url = getattr(settings, "MEDIA_BASE_URL", "") or ""
        if base_url:
            return f"{base_url.rstrip('/')}{url}"
        return url

    @property
    def avatar_url(self) -> str:
        """
        Return either the uploaded avatar URL or a deterministic placeholder.
        """
        if self.avatar:
            try:
                return self._build_media_url(self.avatar.url)
            except ValueError:
                # Missing file or storage misconfiguration; fall back to placeholder.
                pass

        seed = quote_plus(self._avatar_placeholder_seed())
        return f"https://api.dicebear.com/7.x/initials/svg?seed={seed}&backgroundColor=5B8CA6"

    @property
    def avatar_uploaded(self) -> bool:
        return bool(self.avatar)


class LoginEvent(models.Model):
    """Immutable audit record for every login event."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="login_events",
        on_delete=models.CASCADE,
    )
    ip = models.GenericIPAddressField()
    user_agent = models.TextField()
    ua_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Lowercase hex hash of the user agent string.",
    )
    is_new_device = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "created_at"), name="login_event_user_created_idx"),
            models.Index(fields=("user", "ua_hash"), name="login_event_user_hash_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.ip} ({self.created_at:%Y-%m-%d %H:%M:%S})"


class PasswordResetChallenge(models.Model):
    """Stores hashed reset codes and metadata for throttling/verification."""

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    CODE_DIGITS = 6

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="password_reset_challenges",
        on_delete=models.CASCADE,
    )
    channel = models.CharField(max_length=8, choices=Channel.choices)
    contact = models.CharField(max_length=255, help_text="Destination email or E.164 number.")
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "channel"), name="prc_user_channel_idx"),
            models.Index(fields=("channel", "contact"), name="prc_channel_contact_idx"),
            models.Index(fields=("expires_at",), name="prc_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} reset for {self.user}"

    @classmethod
    def generate_code(cls) -> str:
        """Return a zero-padded numeric challenge code."""
        return f"{secrets.randbelow(10**cls.CODE_DIGITS):0{cls.CODE_DIGITS}d}"

    @staticmethod
    def _hash_code(raw_code: str) -> str:
        """Hash reset codes using SHA512 to avoid storing plaintext."""
        return hashlib.sha512(raw_code.encode("utf-8")).hexdigest()

    def set_code(self, raw_code: str) -> None:
        """Hash and persist a new code, resetting attempts and timestamps."""
        self.code_hash = self._hash_code(raw_code)
        self.attempts = 0
        self.consumed = False
        self.last_sent_at = timezone.now()

    def is_expired(self) -> bool:
        """Return True when the challenge can no longer be used."""
        return timezone.now() >= self.expires_at

    def can_attempt(self) -> bool:
        """Check throttling/expiry constraints before verifying a code."""
        if self.consumed:
            return False
        if self.attempts >= self.max_attempts:
            return False
        return not self.is_expired()

    def check_code(self, raw_code: str) -> bool:
        """
        Constant-time verification of a submitted code.

        Callers are responsible for saving the instance after invoking this method.
        """
        if not self.can_attempt():
            return False

        matches = secrets.compare_digest(self._hash_code(raw_code), self.code_hash)
        self.attempts += 1
        if matches:
            self.consumed = True
        return matches


class TwoFactorChallenge(models.Model):
    """Stores hashed 2FA login codes per user/channel/contact."""

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    CODE_DIGITS = 6

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="two_factor_challenges",
        on_delete=models.CASCADE,
    )
    channel = models.CharField(max_length=8, choices=Channel.choices)
    contact = models.CharField(max_length=255, help_text="Destination email or E.164 number.")
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "channel"), name="tfc_user_channel_idx"),
            models.Index(fields=("channel", "contact"), name="tfc_channel_contact_idx"),
            models.Index(fields=("expires_at",), name="tfc_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} 2FA for {self.user}"

    @classmethod
    def generate_code(cls) -> str:
        """Return a zero-padded numeric two-factor code."""
        return f"{secrets.randbelow(10**cls.CODE_DIGITS):0{cls.CODE_DIGITS}d}"

    @staticmethod
    def _hash_code(raw_code: str) -> str:
        """Hash two-factor codes using SHA512 to avoid storing plaintext."""
        return hashlib.sha512(raw_code.encode("utf-8")).hexdigest()

    def set_code(self, raw_code: str) -> None:
        """Persist a new code hash and reset throttling metadata."""
        self.code_hash = self._hash_code(raw_code)
        self.attempts = 0
        self.consumed = False
        self.last_sent_at = timezone.now()

    def is_expired(self) -> bool:
        """Return True when the code is no longer valid."""
        return timezone.now() >= self.expires_at

    def can_attempt(self) -> bool:
        """Check whether another verification attempt can be made."""
        if self.consumed:
            return False
        if self.attempts >= self.max_attempts:
            return False
        return not self.is_expired()

    def check_code(self, raw_code: str) -> bool:
        """
        Constant-time verification of a submitted two-factor code.

        Callers are responsible for saving the instance after invoking this method.
        """
        if not self.can_attempt():
            return False

        matches = secrets.compare_digest(self._hash_code(raw_code), self.code_hash)
        self.attempts += 1
        if matches:
            self.consumed = True
        return matches


class ContactVerificationChallenge(models.Model):
    """Stores verification codes for confirming user email or phone access."""

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"

    CODE_DIGITS = 6

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="contact_verification_challenges",
        on_delete=models.CASCADE,
    )
    channel = models.CharField(max_length=8, choices=Channel.choices)
    contact = models.CharField(max_length=255, help_text="Destination email or E.164 number.")
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("user", "channel"),
                name="cvc_user_channel_idx",
            ),
            models.Index(
                fields=("channel", "contact"),
                name="cvc_channel_contact_idx",
            ),
            models.Index(fields=("expires_at",), name="cvc_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} verification for {self.user}"

    @classmethod
    def generate_code(cls) -> str:
        return f"{secrets.randbelow(10**cls.CODE_DIGITS):0{cls.CODE_DIGITS}d}"

    @staticmethod
    def _hash_code(raw_code: str) -> str:
        return hashlib.sha512(raw_code.encode("utf-8")).hexdigest()

    def set_code(self, raw_code: str) -> None:
        self.code_hash = self._hash_code(raw_code)
        self.attempts = 0
        self.consumed = False
        self.last_sent_at = timezone.now()

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def can_attempt(self) -> bool:
        if self.consumed:
            return False
        if self.attempts >= self.max_attempts:
            return False
        return not self.is_expired()

    def check_code(self, raw_code: str) -> bool:
        if not self.can_attempt():
            return False
        matches = secrets.compare_digest(self._hash_code(raw_code), self.code_hash)
        self.attempts += 1
        if matches:
            self.consumed = True
        return matches
