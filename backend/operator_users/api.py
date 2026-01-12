from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import (
    BooleanField,
    Count,
    ExpressionWrapper,
    F,
    IntegerField,
    Prefetch,
    Value,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from bookings.models import Booking
from notifications import tasks as notification_tasks
from operator_core.api_base import OperatorAPIView, OperatorThrottleMixin
from operator_core.audit import audit
from operator_core.models import OperatorAuditEvent
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_users.filters import OperatorUserFilter
from operator_users.models import UserRiskFlag
from operator_users.serializers import OperatorUserDetailSerializer, OperatorUserListSerializer
from users.api import _safe_notify
from users.models import ContactVerificationChallenge, PasswordResetChallenge, UserFeeOverride

User = get_user_model()

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)

ZERO_INT = Value(0, output_field=IntegerField())


class OperatorUserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


def _annotated_staff_queryset():
    return (
        User.objects.all()
        .select_related("fee_override")
        .annotate(
            listings_count=Count("listings", distinct=True),
            bookings_as_renter_count=Count("bookings_as_renter", distinct=True),
            bookings_as_owner_count=Count("bookings_as_owner", distinct=True),
            disputes_as_owner_count=Count("bookings_as_owner__dispute_cases", distinct=True),
            disputes_as_renter_count=Count("bookings_as_renter__dispute_cases", distinct=True),
        )
        .annotate(
            disputes_count=ExpressionWrapper(
                Coalesce(F("disputes_as_owner_count"), ZERO_INT)
                + Coalesce(F("disputes_as_renter_count"), ZERO_INT),
                output_field=IntegerField(),
            )
        )
        .annotate(
            identity_verified=Coalesce(
                F("payout_account__is_fully_onboarded"),
                Value(False),
                output_field=BooleanField(),
            )
        )
        .prefetch_related(
            Prefetch(
                "risk_flags",
                queryset=UserRiskFlag.objects.filter(active=True)
                .select_related("created_by")
                .order_by("-created_at"),
                to_attr="active_risk_flags",
            )
        )
    )


class OperatorUserListView(OperatorThrottleMixin, generics.ListAPIView):
    serializer_class = OperatorUserListSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorUserFilter
    pagination_class = OperatorUserPagination
    http_method_names = ["get"]

    def get_queryset(self):
        qs = _annotated_staff_queryset()

        ordering = (self.request.query_params.get("ordering") or "newest").strip()

        if ordering == "most_bookings":
            qs = qs.annotate(
                total_bookings_count=ExpressionWrapper(
                    Coalesce(F("bookings_as_owner_count"), ZERO_INT)
                    + Coalesce(F("bookings_as_renter_count"), ZERO_INT),
                    output_field=IntegerField(),
                )
            ).order_by("-total_bookings_count", "-date_joined")
        elif ordering == "most_disputes":
            qs = qs.order_by("-disputes_count", "-date_joined")
        else:
            qs = qs.order_by("-date_joined")

        return qs


class OperatorUserDetailView(OperatorThrottleMixin, generics.RetrieveAPIView):
    serializer_class = OperatorUserDetailSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    http_method_names = ["get"]
    lookup_field = "pk"

    def get_queryset(self):
        recent_bookings_qs = Booking.objects.select_related(
            "listing", "listing__owner", "owner", "renter"
        ).order_by("-created_at")
        return _annotated_staff_queryset().prefetch_related(
            Prefetch("bookings_as_owner", queryset=recent_bookings_qs),
            Prefetch("bookings_as_renter", queryset=recent_bookings_qs),
        )


def _request_ip_and_ua(request):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR", ""
    )
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip, user_agent


class OperatorUserActionBase(OperatorAPIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]

    def _get_user(self, pk: int) -> User:
        return get_object_or_404(User, pk=pk)

    def _require_reason(self, payload) -> str | None:
        reason = (payload.get("reason") or "").strip()
        return reason or None

    def _audit_user(
        self,
        request,
        user: User,
        *,
        action: str,
        reason: str,
        before=None,
        after=None,
        meta=None,
    ):
        ip, ua = _request_ip_and_ua(request)
        audit(
            actor=request.user,
            action=action,
            entity_type=OperatorAuditEvent.EntityType.USER,
            entity_id=str(user.id),
            reason=reason,
            before=before,
            after=after,
            meta=meta,
            ip=ip,
            user_agent=ua,
        )


class OperatorUserSuspendView(OperatorUserActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        user = self._get_user(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        before = {"is_active": user.is_active}
        if user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
        after = {"is_active": user.is_active}
        self._audit_user(
            request,
            user,
            action="operator.user.suspend",
            reason=reason,
            before=before,
            after=after,
        )
        return Response({"ok": True, "user_id": user.id, "is_active": user.is_active})


class OperatorUserReinstateView(OperatorUserActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        user = self._get_user(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        before = {"is_active": user.is_active}
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        after = {"is_active": user.is_active}
        self._audit_user(
            request,
            user,
            action="operator.user.reinstate",
            reason=reason,
            before=before,
            after=after,
        )
        return Response({"ok": True, "user_id": user.id, "is_active": user.is_active})


class OperatorUserSetRestrictionsView(OperatorUserActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        user = self._get_user(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        can_rent = payload.get("can_rent", None)
        can_list = payload.get("can_list", None)
        owner_fee_exempt = payload.get("owner_fee_exempt", None)
        renter_fee_exempt = payload.get("renter_fee_exempt", None)
        fee_expires_at_raw = payload.get("fee_expires_at", None)
        if (
            can_rent is None
            and can_list is None
            and owner_fee_exempt is None
            and renter_fee_exempt is None
            and fee_expires_at_raw is None
        ):
            return Response(
                {
                    "detail": (
                        "one of can_rent, can_list, owner_fee_exempt, "
                        "renter_fee_exempt, or fee_expires_at is required"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        updates = {}
        current_override = getattr(user, "fee_override", None)

        def _dt(val):
            if not val:
                return None
            try:
                return val.isoformat()
            except Exception:
                return str(val)

        before = {
            "can_rent": user.can_rent,
            "can_list": user.can_list,
            "owner_fee_exempt": user.owner_fee_exempt,
            "renter_fee_exempt": user.renter_fee_exempt,
            "fee_expires_at": _dt(getattr(current_override, "expires_at", None)),
        }

        def _normalize_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in ("true", "1", "yes"):
                    return True
                if lowered in ("false", "0", "no"):
                    return False
            return None

        if can_rent is not None:
            parsed = _normalize_bool(can_rent)
            if parsed is None:
                return Response(
                    {"detail": "can_rent must be boolean"}, status=status.HTTP_400_BAD_REQUEST
                )
            updates["can_rent"] = parsed
        if can_list is not None:
            parsed = _normalize_bool(can_list)
            if parsed is None:
                return Response(
                    {"detail": "can_list must be boolean"}, status=status.HTTP_400_BAD_REQUEST
                )
            updates["can_list"] = parsed

        override_updates = {}
        if owner_fee_exempt is not None:
            parsed = _normalize_bool(owner_fee_exempt)
            if parsed is None:
                return Response(
                    {"detail": "owner_fee_exempt must be boolean"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            override_updates["owner_fee_exempt"] = parsed
            updates.setdefault("owner_fee_exempt", parsed)
        if renter_fee_exempt is not None:
            parsed = _normalize_bool(renter_fee_exempt)
            if parsed is None:
                return Response(
                    {"detail": "renter_fee_exempt must be boolean"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            override_updates["renter_fee_exempt"] = parsed
            updates.setdefault("renter_fee_exempt", parsed)

        expires_at_provided = fee_expires_at_raw is not None
        if expires_at_provided:
            normalized_raw = fee_expires_at_raw
            if isinstance(normalized_raw, str) and not normalized_raw.strip():
                normalized_raw = None
            expires_at = None
            if normalized_raw is not None:
                parsed_dt = parse_datetime(str(normalized_raw))
                if parsed_dt is None:
                    return Response(
                        {"detail": "fee_expires_at must be an ISO 8601 datetime"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if timezone.is_naive(parsed_dt):
                    parsed_dt = timezone.make_aware(parsed_dt, timezone.get_current_timezone())
                expires_at = parsed_dt
            override_updates["expires_at"] = expires_at

        if updates:
            for field, value in updates.items():
                setattr(user, field, value)
            update_fields = list(updates.keys())
            user.save(update_fields=update_fields)

        if override_updates:
            if current_override is None:
                override = UserFeeOverride.objects.create(user=user, **override_updates)
            else:
                for field, value in override_updates.items():
                    setattr(current_override, field, value)
                update_fields = list(override_updates.keys())
                if "updated_at" not in update_fields:
                    update_fields.append("updated_at")
                current_override.save(update_fields=update_fields)
                override = current_override
            user.fee_override = override

        after_override = getattr(user, "fee_override", None)
        after = {
            "can_rent": user.can_rent,
            "can_list": user.can_list,
            "owner_fee_exempt": getattr(user, "owner_fee_exempt", False),
            "renter_fee_exempt": getattr(user, "renter_fee_exempt", False),
            "fee_expires_at": _dt(getattr(after_override, "expires_at", None)),
        }
        self._audit_user(
            request,
            user,
            action="operator.user.set_restrictions",
            reason=reason,
            before=before,
            after=after,
        )
        return Response({"ok": True, "user_id": user.id, **after})


class OperatorUserMarkSuspiciousView(OperatorUserActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        user = self._get_user(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        level = (payload.get("level") or "").strip()
        category = (payload.get("category") or "").strip()
        note = (payload.get("note") or "").strip()

        if level not in UserRiskFlag.Level.values:
            return Response({"detail": "invalid level"}, status=status.HTTP_400_BAD_REQUEST)
        if category not in UserRiskFlag.Category.values:
            return Response({"detail": "invalid category"}, status=status.HTTP_400_BAD_REQUEST)

        # Deactivate any previous active flags for this category.
        deactivated = UserRiskFlag.objects.filter(user=user, category=category, active=True).update(
            active=False
        )

        flag = UserRiskFlag.objects.create(
            user=user,
            level=level,
            category=category,
            note=note or None,
            created_by=request.user,
            active=True,
        )

        after = {
            "risk_flag_id": flag.id,
            "level": level,
            "category": category,
            "note": note or "",
            "deactivated_previous": deactivated,
        }
        self._audit_user(
            request,
            user,
            action="operator.user.mark_suspicious",
            reason=reason,
            before=None,
            after=after,
        )
        return Response({"ok": True, "risk_flag_id": flag.id})


class OperatorUserSendPasswordResetView(OperatorUserActionBase):
    http_method_names = ["post"]
    reset_expiry_minutes = 15

    def post(self, request, pk: int):
        user = self._get_user(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        channel = None
        contact = None
        if user.email:
            channel = PasswordResetChallenge.Channel.EMAIL
            contact = user.email
        elif getattr(user, "phone", None):
            channel = PasswordResetChallenge.Channel.SMS
            contact = user.phone
        else:
            return Response(
                {"detail": "user has no contact for password reset"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenge = self._issue_challenge(user, channel, contact)

        self._audit_user(
            request,
            user,
            action="operator.user.send_password_reset",
            reason=reason,
            before=None,
            after={"channel": channel, "challenge_id": challenge.id},
        )
        return Response({"ok": True, "challenge_id": challenge.id})

    def _issue_challenge(self, user: User, channel: str, contact: str) -> PasswordResetChallenge:
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
        now = timezone.now()
        if not challenge or challenge.is_expired():
            challenge = PasswordResetChallenge(user=user, channel=channel, contact=contact)

        raw_code = PasswordResetChallenge.generate_code()
        challenge.expires_at = now + timedelta(minutes=self.reset_expiry_minutes)
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


class OperatorUserResendVerificationView(OperatorUserActionBase):
    http_method_names = ["post"]
    expiry_minutes = 15

    def post(self, request, pk: int):
        user = self._get_user(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        channel = (payload.get("channel") or "").strip()
        if channel not in ContactVerificationChallenge.Channel.values:
            return Response({"detail": "invalid channel"}, status=status.HTTP_400_BAD_REQUEST)

        if channel == ContactVerificationChallenge.Channel.EMAIL:
            contact = user.email
        else:
            contact = getattr(user, "phone", None)

        if not contact:
            return Response({"detail": "contact not available"}, status=status.HTTP_400_BAD_REQUEST)

        challenge = self._issue_challenge(user, channel, contact)

        self._audit_user(
            request,
            user,
            action="operator.user.resend_verification",
            reason=reason,
            before=None,
            after={"channel": channel, "challenge_id": challenge.id},
        )
        return Response({"ok": True, "challenge_id": challenge.id, "channel": channel})

    def _issue_challenge(
        self, user: User, channel: str, contact: str
    ) -> ContactVerificationChallenge:
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
        if not challenge or challenge.is_expired():
            challenge = ContactVerificationChallenge(user=user, channel=channel, contact=contact)

        raw_code = ContactVerificationChallenge.generate_code()
        challenge.expires_at = now + timedelta(minutes=self.expiry_minutes)
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


class OperatorUserRevealView(OperatorUserActionBase):
    http_method_names = ["post"]
    allowed_fields = {"email", "phone", "street_address", "postal_code"}

    def post(self, request, pk: int):
        user = self._get_user(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        fields = payload.get("fields") or ["email", "phone"]
        if not isinstance(fields, list):
            return Response({"detail": "fields must be a list"}, status=status.HTTP_400_BAD_REQUEST)

        normalized = []
        for item in fields:
            name = (item or "").strip()
            if name:
                normalized.append(name)
        if not normalized:
            normalized = ["email", "phone"]

        invalid = [f for f in normalized if f not in self.allowed_fields]
        if invalid:
            return Response(
                {"detail": f"invalid fields: {', '.join(sorted(set(invalid)))}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_payload = {field: getattr(user, field, None) for field in normalized}

        self._audit_user(
            request,
            user,
            action="operator.user.reveal_pii",
            reason=reason,
            before=None,
            after=None,
            meta={"fields": normalized},
        )
        return Response(response_payload, status=status.HTTP_200_OK)
