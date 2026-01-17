from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from operator_core.audit import audit
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_settings.jobs import JOB_REGISTRY
from operator_settings.models import DbSetting, FeatureFlag, MaintenanceBanner, OperatorJobRun
from operator_settings.serializers import (
    DbSettingPutSerializer,
    DbSettingSerializer,
    FeatureFlagPutSerializer,
    FeatureFlagSerializer,
    MaintenanceBannerPutSerializer,
    MaintenanceBannerSerializer,
    OperatorJobRunSerializer,
    OperatorRunJobSerializer,
    is_valid_gst_number,
    normalize_gst_number,
)
from operator_settings.tasks import operator_run_job

logger = logging.getLogger(__name__)

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)


def _request_ip_and_ua(request) -> tuple[str, str]:
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR", ""
    )
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip, user_agent


def _safe_json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(v) for v in value]
    return value


def _user_display(user) -> str | None:
    if not user:
        return None
    full_name = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    if full_name:
        return full_name
    username = getattr(user, "username", "") or getattr(user, "email", "")
    if username:
        return username
    return f"user-{getattr(user, 'pk', '')}".strip("-")


def _db_setting_dict(setting: DbSetting | None) -> dict | None:
    if not setting:
        return None
    return {
        "id": setting.id,
        "key": setting.key,
        "value_type": setting.value_type,
        "value_json": setting.value_json,
        "description": setting.description,
        "effective_at": setting.effective_at,
        "updated_at": setting.updated_at,
        "updated_by_id": setting.updated_by_id,
        "updated_by_name": _user_display(getattr(setting, "updated_by", None)),
    }


def _feature_flag_dict(flag: FeatureFlag | None) -> dict | None:
    if not flag:
        return None
    return {
        "id": flag.id,
        "key": flag.key,
        "enabled": flag.enabled,
        "updated_at": flag.updated_at,
        "updated_by_id": flag.updated_by_id,
    }


def _maintenance_banner_dict(banner: MaintenanceBanner | None) -> dict | None:
    if not banner:
        return None
    return {
        "id": banner.id,
        "enabled": banner.enabled,
        "severity": banner.severity,
        "message": banner.message,
        "updated_at": banner.updated_at,
        "updated_by_id": banner.updated_by_id,
    }


def _current_effective_setting(key: str, *, now: datetime) -> DbSetting | None:
    return (
        DbSetting.objects.filter(key=key)
        .filter(Q(effective_at__isnull=True) | Q(effective_at__lte=now))
        .order_by(F("effective_at").desc(nulls_last=True), "-updated_at", "-id")
        .first()
    )


def _current_effective_setting_value(key: str, *, now: datetime, default: object) -> object:
    setting = _current_effective_setting(key, now=now)
    if setting is None:
        return default
    return setting.value_json


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _default_booking_platform_fee_bps() -> int:
    rate = _to_decimal(getattr(settings, "BOOKING_RENTER_FEE_RATE", Decimal("0")))
    return int((rate * Decimal("10000")).to_integral_value(rounding=ROUND_HALF_UP))


def _default_booking_owner_fee_bps() -> int:
    rate = _to_decimal(getattr(settings, "BOOKING_OWNER_FEE_RATE", Decimal("0")))
    return int((rate * Decimal("10000")).to_integral_value(rounding=ROUND_HALF_UP))


class OperatorSettingsView(APIView):
    http_method_names = ["get", "put"]

    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsOperator(), HasOperatorRole.with_roles(["operator_admin"])()]
        return [IsOperator(), HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)()]

    def get(self, request):
        now = timezone.now()
        qs = (
            DbSetting.objects.filter(Q(effective_at__isnull=True) | Q(effective_at__lte=now))
            .order_by("key", F("effective_at").desc(nulls_last=True), "-updated_at", "-id")
            .select_related("updated_by")
        )

        selected: list[DbSetting] = []
        seen: set[str] = set()
        for row in qs:
            if row.key in seen:
                continue
            seen.add(row.key)
            selected.append(row)

        return Response(DbSettingSerializer(selected, many=True).data)

    def put(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        serializer = DbSettingPutSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        key = serializer.validated_data["key"]
        value_type = serializer.validated_data["value_type"]
        value = serializer.validated_data["value"]
        description = serializer.validated_data.get("description") or ""
        effective_at = serializer.validated_data.get("effective_at")
        reason = serializer.validated_data["reason"]

        ip, user_agent = _request_ip_and_ua(request)
        with transaction.atomic():
            now = timezone.now()
            if key == "ORG_GST_REGISTERED" and value is True:
                raw_number = _current_effective_setting_value(
                    "ORG_GST_NUMBER",
                    now=now,
                    default="",
                )
                normalized = normalize_gst_number(str(raw_number or ""))
                if not normalized or not is_valid_gst_number(normalized):
                    return Response(
                        {"detail": "GST number is required when GST registration is enabled."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if key == "ORG_GST_NUMBER":
                gst_enabled = _current_effective_setting_value(
                    "ORG_GST_REGISTERED",
                    now=now,
                    default=False,
                )
                if gst_enabled and not value:
                    return Response(
                        {"detail": "GST number is required when GST registration is enabled."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            before = _db_setting_dict(_current_effective_setting(key, now=now))

            setting = DbSetting.objects.create(
                key=key,
                value_type=value_type,
                value_json=value,
                description=description,
                effective_at=effective_at,
                updated_by=request.user,
            )

            after = _db_setting_dict(setting)
            audit(
                actor=request.user,
                action="operator.settings.put",
                entity_type="db_setting",
                entity_id=key,
                reason=reason,
                before=_safe_json_value(before),
                after=_safe_json_value(after),
                meta=None,
                ip=ip,
                user_agent=user_agent,
            )

        return Response(DbSettingSerializer(setting).data, status=status.HTTP_201_CREATED)


class OperatorSettingsCurrentView(APIView):
    """
    Returns effective values for a curated set of settings, using DbSetting overrides
    when present, and falling back to env/code defaults when not.
    """

    http_method_names = ["get"]

    def get_permissions(self):
        return [IsOperator(), HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)()]

    def get(self, request):
        now = timezone.now()

        defaults: list[tuple[str, str, object]] = [
            (
                "UNVERIFIED_MAX_BOOKING_DAYS",
                DbSetting.ValueType.INT,
                int(getattr(settings, "UNVERIFIED_MAX_BOOKING_DAYS", 0) or 0),
            ),
            (
                "VERIFIED_MAX_BOOKING_DAYS",
                DbSetting.ValueType.INT,
                int(getattr(settings, "VERIFIED_MAX_BOOKING_DAYS", 0) or 0),
            ),
            (
                "UNVERIFIED_MAX_DEPOSIT_CAD",
                DbSetting.ValueType.DECIMAL,
                str(getattr(settings, "UNVERIFIED_MAX_DEPOSIT_CAD", "0")),
            ),
            (
                "UNVERIFIED_MAX_REPLACEMENT_CAD",
                DbSetting.ValueType.DECIMAL,
                str(getattr(settings, "UNVERIFIED_MAX_REPLACEMENT_CAD", "0")),
            ),
            (
                "LISTING_SOFT_DELETE_RETENTION_DAYS",
                DbSetting.ValueType.INT,
                int(getattr(settings, "LISTING_SOFT_DELETE_RETENTION_DAYS", 0) or 0),
            ),
            (
                "S3_MAX_UPLOAD_BYTES",
                DbSetting.ValueType.INT,
                int(getattr(settings, "S3_MAX_UPLOAD_BYTES", 0) or 0),
            ),
            (
                "IMAGE_MAX_UPLOAD_BYTES",
                DbSetting.ValueType.INT,
                int(getattr(settings, "IMAGE_MAX_UPLOAD_BYTES", 0) or 0),
            ),
            (
                "VIDEO_MAX_UPLOAD_BYTES",
                DbSetting.ValueType.INT,
                int(getattr(settings, "VIDEO_MAX_UPLOAD_BYTES", 0) or 0),
            ),
            (
                "IMAGE_MAX_DIMENSION",
                DbSetting.ValueType.INT,
                int(getattr(settings, "IMAGE_MAX_DIMENSION", 0) or 0),
            ),
            (
                "BOOKING_PLATFORM_FEE_BPS",
                DbSetting.ValueType.INT,
                _default_booking_platform_fee_bps(),
            ),
            ("BOOKING_OWNER_FEE_BPS", DbSetting.ValueType.INT, _default_booking_owner_fee_bps()),
            (
                "PROMOTION_PRICE_CENTS",
                DbSetting.ValueType.INT,
                int(getattr(settings, "PROMOTION_PRICE_CENTS", 0) or 0),
            ),
            ("ORG_GST_REGISTERED", DbSetting.ValueType.BOOL, False),
            ("ORG_GST_NUMBER", DbSetting.ValueType.STR, ""),
            ("ORG_GST_RATE", DbSetting.ValueType.DECIMAL, "0.05"),
            ("DISPUTE_FILING_WINDOW_HOURS", DbSetting.ValueType.INT, 24),
            ("DISPUTE_REBUTTAL_WINDOW_HOURS", DbSetting.ValueType.INT, 24),
            ("DISPUTE_NO_SHOW_REBUTTAL_HOURS", DbSetting.ValueType.INT, 2),
            ("DISPUTE_APPEAL_WINDOW_DAYS", DbSetting.ValueType.INT, 5),
            ("DISPUTE_ALLOW_LATE_SAFETY_FRAUD", DbSetting.ValueType.BOOL, True),
            (
                "DISPUTE_VIDEO_SCAN_SAMPLE_BYTES",
                DbSetting.ValueType.INT,
                int(getattr(settings, "DISPUTE_VIDEO_SCAN_SAMPLE_BYTES", 0) or 0),
            ),
            (
                "DISPUTE_VIDEO_SCAN_SAMPLE_FRAMES",
                DbSetting.ValueType.INT,
                int(getattr(settings, "DISPUTE_VIDEO_SCAN_SAMPLE_FRAMES", 0) or 0),
            ),
        ]

        keys = [key for key, _, _ in defaults]
        qs = (
            DbSetting.objects.filter(key__in=keys)
            .filter(Q(effective_at__isnull=True) | Q(effective_at__lte=now))
            .order_by("key", F("effective_at").desc(nulls_last=True), "-updated_at", "-id")
            .select_related("updated_by")
        )

        selected: dict[str, DbSetting] = {}
        for row in qs:
            if row.key in selected:
                continue
            selected[row.key] = row

        out: list[dict] = []
        for key, value_type, default_value in defaults:
            row = selected.get(key)
            if row is None:
                out.append(
                    _safe_json_value(
                        {
                            "key": key,
                            "value_type": value_type,
                            "value_json": default_value,
                            "description": "",
                            "effective_at": None,
                            "updated_at": None,
                            "updated_by_id": None,
                            "updated_by_name": None,
                            "source": "default",
                        }
                    )
                )
            else:
                updated_by = getattr(row, "updated_by", None)
                out.append(
                    _safe_json_value(
                        {
                            "key": row.key,
                            "value_type": row.value_type,
                            "value_json": row.value_json,
                            "description": row.description,
                            "effective_at": row.effective_at,
                            "updated_at": row.updated_at,
                            "updated_by_id": row.updated_by_id,
                            "updated_by_name": _user_display(updated_by),
                            "source": "db",
                        }
                    )
                )

        return Response(out)


class OperatorFeatureFlagsView(APIView):
    http_method_names = ["get", "put"]

    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsOperator(), HasOperatorRole.with_roles(["operator_admin"])()]
        return [IsOperator(), HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)()]

    def get(self, request):
        qs = FeatureFlag.objects.all().order_by("key").select_related("updated_by")
        return Response(FeatureFlagSerializer(qs, many=True).data)

    def put(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        serializer = FeatureFlagPutSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        key = serializer.validated_data["key"]
        enabled = serializer.validated_data["enabled"]
        reason = serializer.validated_data["reason"]

        ip, user_agent = _request_ip_and_ua(request)
        with transaction.atomic():
            flag = FeatureFlag.objects.select_for_update().filter(key=key).first()
            before = _feature_flag_dict(flag)
            if flag is None:
                flag = FeatureFlag.objects.create(key=key, enabled=enabled, updated_by=request.user)
            else:
                flag.enabled = enabled
                flag.updated_by = request.user
                flag.save(update_fields=["enabled", "updated_by", "updated_at"])

            after = _feature_flag_dict(flag)
            audit(
                actor=request.user,
                action="operator.feature_flags.put",
                entity_type="feature_flag",
                entity_id=key,
                reason=reason,
                before=_safe_json_value(before),
                after=_safe_json_value(after),
                meta=None,
                ip=ip,
                user_agent=user_agent,
            )

        return Response(FeatureFlagSerializer(flag).data, status=status.HTTP_200_OK)


class OperatorMaintenanceView(APIView):
    http_method_names = ["get", "put"]

    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsOperator(), HasOperatorRole.with_roles(["operator_admin"])()]
        return [IsOperator(), HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)()]

    def get(self, request):
        banner = MaintenanceBanner.objects.order_by("-updated_at", "-id").first()
        if banner is None:
            return Response(
                {
                    "enabled": False,
                    "severity": MaintenanceBanner.Severity.INFO,
                    "message": "",
                    "updated_at": None,
                    "updated_by_id": None,
                }
            )

        data = MaintenanceBannerSerializer(banner).data
        return Response(data)

    def put(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        serializer = MaintenanceBannerPutSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        enabled = serializer.validated_data["enabled"]
        severity = serializer.validated_data["severity"]
        message = serializer.validated_data.get("message") or ""
        reason = serializer.validated_data["reason"]

        ip, user_agent = _request_ip_and_ua(request)
        with transaction.atomic():
            banner = (
                MaintenanceBanner.objects.select_for_update().order_by("-updated_at", "-id").first()
            )
            before = _maintenance_banner_dict(banner)
            if banner is None:
                banner = MaintenanceBanner.objects.create(
                    enabled=enabled,
                    severity=severity,
                    message=message,
                    updated_by=request.user,
                )
            else:
                banner.enabled = enabled
                banner.severity = severity
                banner.message = message
                banner.updated_by = request.user
                banner.save(
                    update_fields=["enabled", "severity", "message", "updated_by", "updated_at"]
                )

            after = _maintenance_banner_dict(banner)
            audit(
                actor=request.user,
                action="operator.maintenance.put",
                entity_type="maintenance_banner",
                entity_id=str(getattr(banner, "id", "")),
                reason=reason,
                before=_safe_json_value(before),
                after=_safe_json_value(after),
                meta=None,
                ip=ip,
                user_agent=user_agent,
            )

        return Response(MaintenanceBannerSerializer(banner).data, status=status.HTTP_200_OK)


class OperatorJobRunsView(APIView):
    http_method_names = ["get"]

    def get_permissions(self):
        return [IsOperator(), HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)()]

    def get(self, request):
        qs = OperatorJobRun.objects.select_related("requested_by").order_by("-created_at")[:200]
        return Response(OperatorJobRunSerializer(qs, many=True).data)


class OperatorRunJobView(APIView):
    http_method_names = ["post"]

    def get_permissions(self):
        return [IsOperator(), HasOperatorRole.with_roles(["operator_admin"])()]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        serializer = OperatorRunJobSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data["name"]
        params = serializer.validated_data.get("params") or {}
        reason = serializer.validated_data["reason"]

        if name not in JOB_REGISTRY:
            return Response({"detail": "Unknown job name"}, status=status.HTTP_400_BAD_REQUEST)

        ip, user_agent = _request_ip_and_ua(request)
        job_run: OperatorJobRun
        with transaction.atomic():
            job_run = OperatorJobRun.objects.create(
                name=name,
                params=params,
                requested_by=request.user,
                status=OperatorJobRun.Status.QUEUED,
            )
            audit(
                actor=request.user,
                action="operator.jobs.run",
                entity_type="operator_job_run",
                entity_id=str(job_run.id),
                reason=reason,
                before=None,
                after={"job_run_id": job_run.id, "name": name, "params": params},
                meta=None,
                ip=ip,
                user_agent=user_agent,
            )

        try:
            operator_run_job.delay(job_run.id)
        except Exception as exc:
            now = timezone.now()
            job_run.status = OperatorJobRun.Status.FAILED
            job_run.output_json = {"ok": False, "error": _safe_json_value({"message": str(exc)})}
            job_run.finished_at = now
            job_run.save(update_fields=["status", "output_json", "finished_at"])
            logger.warning(
                "Failed to enqueue operator job",
                extra={"job_run_id": job_run.id, "name": name},
                exc_info=True,
            )
            return Response(
                {"detail": "Failed to enqueue job"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"ok": True, "job_run_id": job_run.id}, status=status.HTTP_202_ACCEPTED)
