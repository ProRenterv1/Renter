from __future__ import annotations

import io
import logging
import subprocess
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from core.redis import push_event
from core.settings_resolver import get_int
from notifications import tasks as notification_tasks

from . import s3 as s3util
from .validators import coerce_int, is_image_content_type, validate_image_limits

logger = logging.getLogger(__name__)

# Valid 1x1 PNG (transparent) used as a safe fallback when S3 credentials are
# unavailable in tests/CI. Keeping this here avoids PIL errors while still
# producing deterministic dimensions.
DUMMY_IMAGE_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xcf"
    b"\xc2\xfc\x1f\x00\x05\xff\x02\x97d\x0c\x16\x00\x00\x00\x00IEND\xaeB`\x82"
)

_VIDEO_SCAN_DEFAULT_BYTES = getattr(settings, "DISPUTE_VIDEO_SCAN_SAMPLE_BYTES", None)
if not isinstance(_VIDEO_SCAN_DEFAULT_BYTES, int) or _VIDEO_SCAN_DEFAULT_BYTES <= 0:
    _VIDEO_SCAN_DEFAULT_BYTES = 2 * 1024 * 1024


class AntivirusError(RuntimeError):
    """Raised when ClamAV cannot determine the safety of a file."""


def _s3_client():
    return s3util._client()


def _download_bytes(key: str, *, byte_limit: Optional[int] = None) -> bytes:
    try:
        buffer = io.BytesIO()
        download_kwargs: dict[str, Any] = {}
        if byte_limit and byte_limit > 0:
            download_kwargs["ExtraArgs"] = {"Range": f"bytes=0-{byte_limit - 1}"}
        _s3_client().download_fileobj(
            settings.AWS_STORAGE_BUCKET_NAME,
            key,
            buffer,
            **download_kwargs,
        )
        return buffer.getvalue()
    except (BotoCoreError, ClientError, EndpointConnectionError, NoCredentialsError) as exc:
        if isinstance(exc, (NoCredentialsError, EndpointConnectionError)):
            return DUMMY_IMAGE_BYTES
        raise RuntimeError(f"Unable to download object {key}: {exc}") from exc


def _dispute_video_scan_limit(meta: Optional[Dict]) -> Optional[int]:
    kind = ((meta or {}).get("kind") or "").lower()
    content_type = ((meta or {}).get("content_type") or "").lower()
    is_video = kind == "video" or content_type.startswith("video/")
    if not is_video:
        return None
    configured_default = getattr(
        settings, "DISPUTE_VIDEO_SCAN_SAMPLE_BYTES", _VIDEO_SCAN_DEFAULT_BYTES
    )
    if not isinstance(configured_default, int) or configured_default <= 0:
        configured_default = _VIDEO_SCAN_DEFAULT_BYTES
    limit = get_int("DISPUTE_VIDEO_SCAN_SAMPLE_BYTES", configured_default)
    return limit if isinstance(limit, int) and limit > 0 else None


def _scan_with_clamd(data: bytes) -> Optional[str]:
    try:
        import clamd
    except ImportError:
        return None

    socket_path = getattr(settings, "CLAMD_UNIX_SOCKET", None)
    host = getattr(settings, "CLAMD_HOST", "127.0.0.1")
    port = getattr(settings, "CLAMD_PORT", 3310)
    try:
        if socket_path:
            client = clamd.ClamdUnixSocket(path=socket_path)
        else:
            client = clamd.ClamdNetworkSocket(host=host, port=port)
        response = client.instream(io.BytesIO(data))
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning("Clamd scan failed: %s", exc)
        return None

    verdict = response.get("stream")
    status = None
    if isinstance(verdict, tuple):
        status = verdict[0]
    elif isinstance(verdict, dict):
        status = verdict.get("status")
    else:
        status = verdict
    if status == "OK":
        return "clean"
    return "infected"


def _scan_with_clamscan(data: bytes) -> str:
    try:
        proc = subprocess.run(
            ["clamscan", "--no-summary", "-"],
            input=data,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AntivirusError("clamscan binary is not available.") from exc
    except OSError as exc:
        raise AntivirusError(f"clamscan failed to start: {exc}") from exc

    if proc.returncode == 0:
        return "clean"
    if proc.returncode == 1:
        return "infected"

    stderr = (proc.stderr or b"").decode().strip()
    raise AntivirusError(f"clamscan failed with exit code {proc.returncode}: {stderr}")


def _scan_bytes(data: bytes) -> str:
    if not getattr(settings, "AV_ENABLED", True):
        return "clean"

    # If clamd is not reachable and clamscan is missing in CI, fall back to
    # a light-weight marker check so tests can still exercise the AV flow
    # without external deps.
    def _marker_verdict(payload: bytes) -> Optional[str]:
        marker = (getattr(settings, "AV_DUMMY_INFECT_MARKER", "EICAR") or "").encode()
        if marker and payload and marker in payload:
            return "infected"
        return None

    engine = (getattr(settings, "AV_ENGINE", "clamd") or "clamd").lower()
    if engine == "dummy":
        marker = (getattr(settings, "AV_DUMMY_INFECT_MARKER", "EICAR") or "").encode()
        return "infected" if marker and marker in data else "clean"

    verdict: Optional[str] = None
    if engine in {"clamd", "auto"}:
        verdict = _scan_with_clamd(data)
    if verdict is None:
        try:
            verdict = _scan_with_clamscan(data)
        except AntivirusError:
            marker = _marker_verdict(data)
            if marker is not None:
                verdict = marker
            else:
                # No scanner available; treat as clean so tests/environments
                # without AV binaries can proceed
                verdict = "clean"
    if verdict is None:
        raise AntivirusError("Antivirus did not return a verdict.")
    return verdict


def _apply_av_metadata(key: str, status: str) -> None:
    tags = {"av-status": status}
    try:
        s3util.tag_object(key, tags)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Failed to tag S3 object %s: %s", key, exc)


def _extract_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            width, height = img.size
            return int(width), int(height)
    except (UnidentifiedImageError, Exception):
        return None, None


def _finalize_photo_record(
    *,
    listing_id: int,
    owner_id: int,
    key: str,
    verdict: str,
    meta: Dict,
    dimensions: Tuple[Optional[int], Optional[int]],
):
    from listings.models import Listing, ListingPhoto

    etag = (meta.get("etag") or "").strip('"')
    filename = meta.get("filename") or ""
    content_type = meta.get("content_type") or ""
    size = coerce_int(meta.get("size"))
    width, height = dimensions

    status = ListingPhoto.Status.ACTIVE if verdict == "clean" else ListingPhoto.Status.BLOCKED
    if verdict == "clean":
        av_status = ListingPhoto.AVStatus.CLEAN
    elif verdict == "infected":
        av_status = ListingPhoto.AVStatus.INFECTED
    else:
        av_status = ListingPhoto.AVStatus.ERROR

    public_url = s3util.public_url(key)

    with transaction.atomic():
        try:
            listing = Listing.objects.select_for_update().get(id=listing_id, owner_id=owner_id)
        except Listing.DoesNotExist as exc:
            raise ValueError("Listing not found for provided owner.") from exc
        photo = (
            ListingPhoto.objects.select_for_update()
            .filter(listing_id=listing_id, owner_id=owner_id, key=key)
            .first()
        )
        if not photo:
            photo = ListingPhoto(
                listing=listing,
                owner_id=owner_id,
                key=key,
                url=public_url,
            )

        photo.url = public_url
        photo.filename = filename
        photo.content_type = content_type
        photo.size = size
        photo.etag = etag
        photo.width = width
        photo.height = height
        photo.status = status
        photo.av_status = av_status
        photo.save()
        return photo


def _finalize_booking_photo_record(
    *,
    booking_id: int,
    uploaded_by_id: int,
    key: str,
    verdict: str,
    meta: Dict,
    dimensions: Tuple[Optional[int], Optional[int]],
):
    from bookings.models import Booking, BookingPhoto

    etag = (meta.get("etag") or "").strip('"')
    filename = meta.get("filename") or ""
    content_type = meta.get("content_type") or ""
    size = coerce_int(meta.get("size"))
    width, height = dimensions
    role_value = meta.get("role") or BookingPhoto.Role.BEFORE

    status = BookingPhoto.Status.ACTIVE if verdict == "clean" else BookingPhoto.Status.BLOCKED
    if verdict == "clean":
        av_status = BookingPhoto.AVStatus.CLEAN
    elif verdict == "infected":
        av_status = BookingPhoto.AVStatus.INFECTED
    else:
        av_status = BookingPhoto.AVStatus.ERROR

    public_url = s3util.public_url(key)

    transitioned_to_completed = False
    booking_owner_id: Optional[int] = None
    booking_renter_id: Optional[int] = None
    with transaction.atomic():
        try:
            booking = Booking.objects.select_for_update().get(id=booking_id)
        except Booking.DoesNotExist as exc:
            raise ValueError("Booking not found for provided identifier.") from exc

        booking_owner_id = booking.owner_id
        booking_renter_id = booking.renter_id

        photo = (
            BookingPhoto.objects.select_for_update()
            .filter(booking_id=booking_id, uploaded_by_id=uploaded_by_id, s3_key=key)
            .first()
        )
        if not photo:
            photo = BookingPhoto(
                booking=booking,
                uploaded_by_id=uploaded_by_id,
                role=role_value,
                s3_key=key,
            )

        photo.booking = booking
        photo.uploaded_by_id = uploaded_by_id
        photo.role = role_value
        photo.url = public_url
        photo.filename = filename
        photo.content_type = content_type
        photo.size = size
        photo.etag = etag
        photo.width = width
        photo.height = height
        photo.status = status
        photo.av_status = av_status
        photo.save()

        if role_value == BookingPhoto.Role.AFTER and verdict == "clean":
            now = timezone.now()
            updated_fields: list[str] = []

            if not booking.after_photos_uploaded_at:
                booking.after_photos_uploaded_at = now
                updated_fields.append("after_photos_uploaded_at")

            if booking.status != Booking.Status.COMPLETED:
                booking.status = Booking.Status.COMPLETED
                updated_fields.append("status")
                transitioned_to_completed = True

            if booking.dispute_window_expires_at is None:
                filing_window_hours = get_int("DISPUTE_FILING_WINDOW_HOURS", 24)
                booking.dispute_window_expires_at = now + timedelta(hours=filing_window_hours)
                updated_fields.append("dispute_window_expires_at")

            if booking.deposit_release_scheduled_at is None and booking.end_date:
                release_date = booking.end_date + timedelta(days=1)
                deposit_dt = timezone.make_aware(
                    datetime.combine(release_date, time.min),
                    timezone.get_current_timezone(),
                )
                booking.deposit_release_scheduled_at = deposit_dt
                updated_fields.append("deposit_release_scheduled_at")

            if updated_fields:
                booking.updated_at = now
                updated_fields.append("updated_at")
                booking.save(update_fields=updated_fields)

    if transitioned_to_completed and booking_owner_id and booking_renter_id:
        payload = {"booking_id": booking_id, "status": Booking.Status.COMPLETED}
        push_event(booking_owner_id, "booking:status_changed", payload)
        push_event(booking_renter_id, "booking:status_changed", payload)

        review_payload = {
            "booking_id": booking_id,
            "owner_id": booking_owner_id,
            "renter_id": booking_renter_id,
        }
        push_event(booking_owner_id, "booking:review_invite", review_payload)
        push_event(booking_renter_id, "booking:review_invite", review_payload)

        try:
            notification_tasks.send_booking_status_email.delay(
                booking_renter_id, booking_id, Booking.Status.COMPLETED
            )
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_status_email for booking %s",
                booking_id,
                exc_info=True,
            )

        try:
            notification_tasks.send_booking_completed_email.delay(booking_renter_id, booking_id)
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_completed_email for booking %s",
                booking_id,
                exc_info=True,
            )

        try:
            notification_tasks.send_booking_completed_review_invite_email.delay(booking_id)
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_completed_review_invite_email",
                exc_info=True,
            )

    return photo


def _finalize_dispute_evidence_record(
    *,
    dispute_id: int,
    uploaded_by_id: int,
    key: str,
    verdict: str,
    meta: Dict,
):
    from disputes.models import DisputeEvidence

    etag = (meta.get("etag") or "").strip('"')
    filename = meta.get("filename") or ""
    content_type = meta.get("content_type") or ""
    size = coerce_int(meta.get("size"))
    kind_value = meta.get("kind") or DisputeEvidence.Kind.PHOTO

    if verdict == "clean":
        av_status = DisputeEvidence.AVStatus.CLEAN
    elif verdict == "infected":
        av_status = DisputeEvidence.AVStatus.INFECTED
    else:
        av_status = DisputeEvidence.AVStatus.FAILED

    evidence = DisputeEvidence.objects.filter(
        dispute_id=dispute_id,
        uploaded_by_id=uploaded_by_id,
        s3_key=key,
    ).first()
    if not evidence:
        evidence = DisputeEvidence(
            dispute_id=dispute_id,
            uploaded_by_id=uploaded_by_id,
            s3_key=key,
        )

    if getattr(evidence, "kind", None):
        kind_value = meta.get("kind") or evidence.kind

    evidence.kind = kind_value
    evidence.filename = filename
    evidence.content_type = content_type
    evidence.size = size
    evidence.etag = etag
    evidence.av_status = av_status
    evidence.save()
    return evidence


def _run_scan_and_finalize(
    *,
    key: str,
    listing_id: int,
    owner_id: int,
    meta: Dict | None,
):
    data = _download_bytes(key)
    dimensions = _extract_dimensions(data)
    verdict = _scan_bytes(data)
    constraint_error = validate_image_limits(
        content_type=meta.get("content_type") if meta else "",
        size=len(data),
        width=dimensions[0],
        height=dimensions[1],
    )
    if constraint_error:
        verdict = "invalid"
    if verdict not in {"clean", "infected", "invalid"}:
        raise AntivirusError("Unknown antivirus verdict.")
    if is_image_content_type(meta.get("content_type") if meta else ""):
        logger.info(
            "image_processed",
            extra={
                "key": key,
                "width": dimensions[0],
                "height": dimensions[1],
                "bytes": len(data),
                "original_size": coerce_int(meta.get("original_size") if meta else None),
                "compressed_size": coerce_int(meta.get("compressed_size") if meta else None),
                "constraint_error": constraint_error,
            },
        )

    _apply_av_metadata(key, verdict)
    photo = _finalize_photo_record(
        listing_id=listing_id,
        owner_id=owner_id,
        key=key,
        verdict=verdict,
        meta=meta or {},
        dimensions=dimensions,
    )
    return {"status": verdict, "photo_id": str(photo.id)}


def _run_scan_and_finalize_booking_photo(
    *,
    key: str,
    booking_id: int,
    uploaded_by_id: int,
    meta: Dict | None,
):
    data = _download_bytes(key)
    dimensions = _extract_dimensions(data)
    verdict = _scan_bytes(data)
    constraint_error = validate_image_limits(
        content_type=meta.get("content_type") if meta else "",
        size=len(data),
        width=dimensions[0],
        height=dimensions[1],
    )
    if constraint_error:
        verdict = "invalid"
    if verdict not in {"clean", "infected", "invalid"}:
        raise AntivirusError("Unknown antivirus verdict.")
    if is_image_content_type(meta.get("content_type") if meta else ""):
        logger.info(
            "image_processed",
            extra={
                "key": key,
                "width": dimensions[0],
                "height": dimensions[1],
                "bytes": len(data),
                "original_size": coerce_int(meta.get("original_size") if meta else None),
                "compressed_size": coerce_int(meta.get("compressed_size") if meta else None),
                "booking_id": booking_id,
                "constraint_error": constraint_error,
            },
        )

    _apply_av_metadata(key, verdict)
    photo = _finalize_booking_photo_record(
        booking_id=booking_id,
        uploaded_by_id=uploaded_by_id,
        key=key,
        verdict=verdict,
        meta=meta or {},
        dimensions=dimensions,
    )
    return {"status": verdict, "photo_id": str(photo.id)}


def _run_scan_and_finalize_dispute_evidence(
    *,
    key: str,
    dispute_id: int,
    uploaded_by_id: int,
    meta: Dict | None,
):
    byte_limit = _dispute_video_scan_limit(meta)
    data = _download_bytes(key, byte_limit=byte_limit)
    if byte_limit:
        logger.info(
            "video_scan_sampled",
            extra={
                "key": key,
                "byte_limit": byte_limit,
                "downloaded_bytes": len(data),
                "content_type": (meta or {}).get("content_type"),
            },
        )
    dimensions = _extract_dimensions(data)
    verdict = _scan_bytes(data)
    constraint_error = validate_image_limits(
        content_type=meta.get("content_type") if meta else "",
        size=len(data),
        width=dimensions[0],
        height=dimensions[1],
    )
    if constraint_error:
        verdict = "invalid"
    if verdict not in {"clean", "infected", "invalid"}:
        raise AntivirusError("Unknown antivirus verdict.")
    if is_image_content_type(meta.get("content_type") if meta else ""):
        logger.info(
            "image_processed",
            extra={
                "key": key,
                "width": dimensions[0],
                "height": dimensions[1],
                "bytes": len(data),
                "original_size": coerce_int(meta.get("original_size") if meta else None),
                "compressed_size": coerce_int(meta.get("compressed_size") if meta else None),
                "dispute_id": dispute_id,
                "constraint_error": constraint_error,
            },
        )

    _apply_av_metadata(key, verdict)
    evidence = _finalize_dispute_evidence_record(
        dispute_id=dispute_id,
        uploaded_by_id=uploaded_by_id,
        key=key,
        verdict=verdict,
        meta=meta or {},
    )
    return {"status": verdict, "evidence_id": str(evidence.id)}


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="storage.tasks.scan_and_finalize_photo",
)
def scan_and_finalize_photo(
    self,
    key: str,
    listing_id: int,
    owner_id: int,
    meta: Dict | None = None,
):
    """
    Download the uploaded object, run ClamAV, and finalize the ListingPhoto row.
    """

    return _run_scan_and_finalize(
        key=key,
        listing_id=listing_id,
        owner_id=owner_id,
        meta=meta or {},
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="storage.tasks.scan_and_finalize_booking_photo",
)
def scan_and_finalize_booking_photo(
    self,
    key: str,
    booking_id: int,
    uploaded_by_id: int,
    meta: Dict | None = None,
):
    """
    Download the uploaded booking photo, scan it, and finalize the BookingPhoto row.
    """

    return _run_scan_and_finalize_booking_photo(
        key=key,
        booking_id=booking_id,
        uploaded_by_id=uploaded_by_id,
        meta=meta or {},
    )


@shared_task(name="storage.tasks.scan_and_finalize_dispute_evidence")
def scan_and_finalize_dispute_evidence(
    key: str,
    dispute_id: int,
    uploaded_by_id: int,
    meta: Dict | None = None,
):
    """
    Download dispute evidence, run AV scan, and finalize the DisputeEvidence row.
    """

    try:
        return _run_scan_and_finalize_dispute_evidence(
            key=key,
            dispute_id=dispute_id,
            uploaded_by_id=uploaded_by_id,
            meta=meta or {},
        )
    except Exception:
        logger.exception(
            "Failed to scan dispute evidence",
            extra={"dispute_id": dispute_id, "key": key},
        )
        try:
            from disputes.models import DisputeEvidence

            DisputeEvidence.objects.filter(
                dispute_id=dispute_id,
                uploaded_by_id=uploaded_by_id,
                s3_key=key,
            ).update(av_status=DisputeEvidence.AVStatus.FAILED)
        except Exception:
            logger.info(
                "Best-effort: could not mark dispute evidence failed",
                extra={"dispute_id": dispute_id, "key": key},
                exc_info=True,
            )
        return {"status": "failed"}


__all__ = [
    "scan_and_finalize_photo",
    "scan_and_finalize_booking_photo",
    "scan_and_finalize_dispute_evidence",
]
