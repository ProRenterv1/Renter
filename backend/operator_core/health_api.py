from __future__ import annotations

import logging
import time
from typing import Any, Dict

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.redis import get_redis_client
from operator_core.permissions import HasOperatorRole, IsOperator
from storage import s3 as storage_s3

logger = logging.getLogger(__name__)

CELERY_HEARTBEAT_KEY = "ops:celery:last_seen"
CELERY_STALE_SECONDS = 120

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)


def _error_payload(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return f"{exc.__class__.__name__}: {message}"


class OperatorHealthView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    http_method_names = ["get"]

    def get(self, request):
        checks: Dict[str, Dict[str, Any]] = {}
        overall_ok = True

        # --- DB ---
        db_ok = False
        db_payload: Dict[str, Any] = {"ok": False}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db_ok = True
            db_payload["ok"] = True
        except Exception as exc:
            db_payload["error"] = _error_payload(exc)
        checks["db"] = db_payload
        overall_ok = overall_ok and db_ok

        # --- Pgbouncer ---
        pgbouncer_payload: Dict[str, Any] = {"ok": False}
        try:
            engine = connection.settings_dict.get("ENGINE", "")
            if "sqlite" in engine:
                pgbouncer_payload = {"ok": True, "skipped": True}
            else:
                try:
                    import psycopg  # type: ignore

                    pg_connect = psycopg.connect
                except ImportError:
                    try:
                        import psycopg2  # type: ignore

                        pg_connect = psycopg2.connect
                    except ImportError as exc:
                        raise RuntimeError(
                            "psycopg (v3) or psycopg2 is required for pgbouncer check"
                        ) from exc

                host = connection.settings_dict.get("HOST") or "localhost"
                port = connection.settings_dict.get("PORT") or 5432
                user = connection.settings_dict.get("USER") or ""
                password = connection.settings_dict.get("PASSWORD") or ""
                if not user:
                    raise RuntimeError("DATABASE user is not configured")
                with pg_connect(
                    dbname="pgbouncer",
                    user=user,
                    password=password,
                    host=host,
                    port=port,
                    connect_timeout=3,
                ) as pgconn:
                    pgconn.autocommit = True
                    with pgconn.cursor() as cursor:
                        cursor.execute("SHOW POOLS;")
                        rows = cursor.fetchall()
                        columns = [col.name for col in cursor.description]
                pool_dicts = [dict(zip(columns, row)) for row in rows]
                cl_active = sum(int(row.get("cl_active") or 0) for row in pool_dicts)
                cl_waiting = sum(int(row.get("cl_waiting") or 0) for row in pool_dicts)
                sv_active = sum(int(row.get("sv_active") or 0) for row in pool_dicts)
                sv_idle = sum(int(row.get("sv_idle") or 0) for row in pool_dicts)
                pool_mode = pool_dicts[0].get("pool_mode") if pool_dicts else ""
                pgbouncer_payload.update(
                    {
                        "ok": True,
                        "pool_count": len(pool_dicts),
                        "cl_active": cl_active,
                        "cl_waiting": cl_waiting,
                        "sv_active": sv_active,
                        "sv_idle": sv_idle,
                        "pool_mode": str(pool_mode) if pool_mode is not None else "",
                    }
                )
        except Exception as exc:
            pgbouncer_payload["error"] = _error_payload(exc)
        checks["pgbouncer"] = pgbouncer_payload
        overall_ok = overall_ok and bool(pgbouncer_payload.get("ok"))

        # --- Redis ---
        redis_ok = False
        redis_payload: Dict[str, Any] = {"ok": False}
        redis_client = None
        try:
            redis_client = get_redis_client()
            redis_ok = bool(redis_client.ping())
            redis_payload["ok"] = redis_ok
        except Exception as exc:
            redis_payload["error"] = _error_payload(exc)
        checks["redis"] = redis_payload
        overall_ok = overall_ok and redis_ok

        # --- Celery heartbeat ---
        celery_payload: Dict[str, Any] = {
            "ok": False,
            "last_seen_epoch": None,
            "stale": True,
        }
        try:
            if redis_client is None:
                redis_client = get_redis_client()
            raw = redis_client.get(CELERY_HEARTBEAT_KEY)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            last_seen = float(raw) if raw not in (None, "") else None
            stale = True
            if last_seen is not None:
                stale = (time.time() - last_seen) > CELERY_STALE_SECONDS
            celery_payload["last_seen_epoch"] = last_seen
            celery_payload["stale"] = stale
            celery_payload["ok"] = bool(last_seen is not None and not stale)
        except Exception as exc:
            celery_payload["error"] = _error_payload(exc)
        checks["celery"] = celery_payload
        overall_ok = overall_ok and bool(celery_payload.get("ok"))

        # --- Stripe ---
        stripe_payload: Dict[str, Any] = {"ok": False}
        try:
            secret = (getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
            if not secret:
                raise RuntimeError("STRIPE_SECRET_KEY is not configured")
            import stripe  # type: ignore

            stripe.api_key = secret
            account = stripe.Account.retrieve()
            account_id = getattr(account, "id", None)
            if not account_id and isinstance(account, dict):
                account_id = account.get("id")
            stripe_payload["ok"] = True
            stripe_payload["account_id"] = account_id or ""
        except Exception as exc:
            stripe_payload["error"] = _error_payload(exc)
        checks["stripe"] = stripe_payload
        overall_ok = overall_ok and bool(stripe_payload.get("ok"))

        # --- Twilio ---
        twilio_payload: Dict[str, Any] = {"ok": False, "configured": False}
        try:
            account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
            auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
            configured = bool(account_sid and auth_token)
            twilio_payload["configured"] = configured
            if not configured:
                raise RuntimeError("TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN not configured")
            try:
                from twilio.rest import Client  # type: ignore
            except ImportError as exc:
                raise RuntimeError("twilio SDK not installed") from exc
            Client(account_sid, auth_token)
            twilio_payload["ok"] = True
        except Exception as exc:
            twilio_payload["error"] = _error_payload(exc)
        checks["twilio"] = twilio_payload
        overall_ok = overall_ok and bool(twilio_payload.get("ok"))

        # --- S3 ---
        s3_payload: Dict[str, Any] = {"ok": False}
        try:
            use_s3 = bool(getattr(settings, "USE_S3", False))
            if not use_s3:
                s3_payload = {"ok": True, "skipped": True}
            else:
                bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
                if not bucket:
                    raise RuntimeError("AWS_STORAGE_BUCKET_NAME is not configured")
                s3_payload["bucket"] = bucket
                client = storage_s3._client()
                client.list_objects_v2(Bucket=bucket, MaxKeys=1)
                s3_payload["ok"] = True
        except Exception as exc:
            s3_payload["error"] = _error_payload(exc)
        checks["s3"] = s3_payload
        overall_ok = overall_ok and bool(s3_payload.get("ok"))

        # --- Email ---
        email_backend = getattr(settings, "EMAIL_BACKEND", None)
        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", None)
        email_ok = bool(email_backend and default_from)
        email_payload: Dict[str, Any] = {"ok": email_ok, "backend": email_backend or ""}
        if not email_ok:
            email_payload["error"] = "EMAIL_BACKEND/DEFAULT_FROM_EMAIL not configured"
        checks["email"] = email_payload
        overall_ok = overall_ok and email_ok

        http_status = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({"ok": overall_ok, "checks": checks}, status=http_status)


class OperatorHealthTestEmailView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(["operator_admin"])]
    http_method_names = ["post"]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        to_email = (payload.get("to") or getattr(request.user, "email", "") or "").strip()
        if not to_email:
            return Response({"detail": "to is required"}, status=status.HTTP_400_BAD_REQUEST)

        subject = "[Kitoro] Operator health test email"
        body = (
            "This is a test email sent from /api/operator/health/test-email/ "
            "to verify email configuration."
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
        if not from_email:
            return Response(
                {"detail": "DEFAULT_FROM_EMAIL is not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            from django.core.mail import send_mail

            sent = send_mail(subject, body, from_email, [to_email], fail_silently=False)
        except Exception:
            logger.warning(
                "Health email send failed",
                extra={"to_email": to_email},
                exc_info=True,
            )
            return Response(
                {"detail": "failed to send email"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not sent:
            return Response(
                {"detail": "email backend did not report success"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"ok": True, "to": to_email}, status=status.HTTP_202_ACCEPTED)
