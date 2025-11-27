from __future__ import annotations

import io
import logging
import subprocess
from datetime import datetime, time, timedelta
from typing import Dict, Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from core.redis import push_event
from notifications import tasks as notification_tasks

from . import s3 as s3util

logger = logging.getLogger(__name__)


class AntivirusError(RuntimeError):
    """Raised when ClamAV cannot determine the safety of a file."""


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        region_name=settings.AWS_S3_REGION_NAME,
    )


def _download_bytes(key: str) -> bytes:
    try:
        buffer = io.BytesIO()
        _s3_client().download_fileobj(settings.AWS_STORAGE_BUCKET_NAME, key, buffer)
        return buffer.getvalue()
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"Unable to download object {key}: {exc}") from exc


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

    if proc.returncode == 0:
        return "clean"
    if proc.returncode == 1:
        return "infected"

    stderr = (proc.stderr or b"").decode().strip()
    raise AntivirusError(f"clamscan failed with exit code {proc.returncode}: {stderr}")


def _scan_bytes(data: bytes) -> str:
    if not getattr(settings, "AV_ENABLED", True):
        return "clean"

    engine = (getattr(settings, "AV_ENGINE", "clamd") or "clamd").lower()
    if engine == "dummy":
        marker = (getattr(settings, "AV_DUMMY_INFECT_MARKER", "EICAR") or "").encode()
        return "infected" if marker and marker in data else "clean"

    verdict: Optional[str] = None
    if engine in {"clamd", "auto"}:
        verdict = _scan_with_clamd(data)
    if verdict is None:
        verdict = _scan_with_clamscan(data)
    if verdict is None:
        raise AntivirusError("Antivirus did not return a verdict.")
    return verdict


def _apply_av_metadata(key: str, status: str) -> None:
    tags = {"av-status": status}
    try:
        s3util.tag_object(key, tags)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Failed to tag S3 object %s: %s", key, exc)
    try:
        s3util.set_metadata_copy(key, {"x-av": status})
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Failed to update S3 metadata for %s: %s", key, exc)


def _extract_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            width, height = img.size
            return int(width), int(height)
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None


def _coerce_int(value) -> Optional[int]:
    if value in (None, "", False):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    size = _coerce_int(meta.get("size"))
    width, height = dimensions

    status = ListingPhoto.Status.ACTIVE if verdict == "clean" else ListingPhoto.Status.BLOCKED
    av_status = (
        ListingPhoto.AVStatus.CLEAN if verdict == "clean" else ListingPhoto.AVStatus.INFECTED
    )

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
    size = _coerce_int(meta.get("size"))
    width, height = dimensions
    role_value = meta.get("role") or BookingPhoto.Role.BEFORE

    status = BookingPhoto.Status.ACTIVE if verdict == "clean" else BookingPhoto.Status.BLOCKED
    av_status = (
        BookingPhoto.AVStatus.CLEAN if verdict == "clean" else BookingPhoto.AVStatus.INFECTED
    )

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
                booking.dispute_window_expires_at = now + timedelta(hours=24)
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


def _run_scan_and_finalize(
    *,
    key: str,
    listing_id: int,
    owner_id: int,
    meta: Dict | None,
):
    data = _download_bytes(key)
    verdict = _scan_bytes(data)
    if verdict not in {"clean", "infected"}:
        raise AntivirusError("Unknown antivirus verdict.")

    _apply_av_metadata(key, verdict)
    photo = _finalize_photo_record(
        listing_id=listing_id,
        owner_id=owner_id,
        key=key,
        verdict=verdict,
        meta=meta or {},
        dimensions=_extract_dimensions(data),
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
    verdict = _scan_bytes(data)
    if verdict not in {"clean", "infected"}:
        raise AntivirusError("Unknown antivirus verdict.")

    _apply_av_metadata(key, verdict)
    photo = _finalize_booking_photo_record(
        booking_id=booking_id,
        uploaded_by_id=uploaded_by_id,
        key=key,
        verdict=verdict,
        meta=meta or {},
        dimensions=_extract_dimensions(data),
    )
    return {"status": verdict, "photo_id": str(photo.id)}


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


__all__ = ["scan_and_finalize_photo", "scan_and_finalize_booking_photo"]
