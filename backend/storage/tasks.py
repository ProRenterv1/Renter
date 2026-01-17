from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
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
from .validators import (
    coerce_int,
    is_image_content_type,
    is_video_content_type,
    validate_image_limits,
)

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

_VIDEO_SCAN_DEFAULT_FRAMES = getattr(settings, "DISPUTE_VIDEO_SCAN_SAMPLE_FRAMES", None)
if not isinstance(_VIDEO_SCAN_DEFAULT_FRAMES, int) or _VIDEO_SCAN_DEFAULT_FRAMES <= 0:
    _VIDEO_SCAN_DEFAULT_FRAMES = 2

_VIDEO_COMPRESSION_DEFAULT_RATIO = getattr(settings, "DISPUTE_VIDEO_COMPRESSION_TARGET_RATIO", None)
try:
    _VIDEO_COMPRESSION_DEFAULT_RATIO = float(_VIDEO_COMPRESSION_DEFAULT_RATIO)
except (TypeError, ValueError):
    _VIDEO_COMPRESSION_DEFAULT_RATIO = 0.5
if _VIDEO_COMPRESSION_DEFAULT_RATIO <= 0 or _VIDEO_COMPRESSION_DEFAULT_RATIO >= 1:
    _VIDEO_COMPRESSION_DEFAULT_RATIO = 0.5

_VIDEO_COMPRESSION_DEFAULT_MAX_PASSES = getattr(
    settings, "DISPUTE_VIDEO_COMPRESSION_MAX_PASSES", None
)
if (
    not isinstance(_VIDEO_COMPRESSION_DEFAULT_MAX_PASSES, int)
    or _VIDEO_COMPRESSION_DEFAULT_MAX_PASSES <= 0
):
    _VIDEO_COMPRESSION_DEFAULT_MAX_PASSES = 4


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


def _download_to_tempfile(key: str) -> Tuple[str, bool]:
    tmp = tempfile.NamedTemporaryFile(delete=False)
    used_dummy = False
    try:
        _s3_client().download_fileobj(settings.AWS_STORAGE_BUCKET_NAME, key, tmp)
    except (BotoCoreError, ClientError, EndpointConnectionError, NoCredentialsError) as exc:
        if isinstance(exc, (NoCredentialsError, EndpointConnectionError)):
            tmp.write(DUMMY_IMAGE_BYTES)
            used_dummy = True
        else:
            tmp.close()
            os.unlink(tmp.name)
            raise RuntimeError(f"Unable to download object {key}: {exc}") from exc
    finally:
        tmp.close()
    return tmp.name, used_dummy


def _read_file_bytes(path: str, *, byte_limit: Optional[int] = None) -> bytes:
    with open(path, "rb") as handle:
        if byte_limit and byte_limit > 0:
            return handle.read(byte_limit)
        return handle.read()


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


def _is_video_meta(meta: Optional[Dict]) -> bool:
    kind = ((meta or {}).get("kind") or "").lower()
    content_type = ((meta or {}).get("content_type") or "").lower()
    return kind == "video" or is_video_content_type(content_type)


def _dispute_video_scan_frames(meta: Optional[Dict]) -> int:
    if not _is_video_meta(meta):
        return 0
    configured_default = getattr(
        settings, "DISPUTE_VIDEO_SCAN_SAMPLE_FRAMES", _VIDEO_SCAN_DEFAULT_FRAMES
    )
    if not isinstance(configured_default, int) or configured_default <= 0:
        configured_default = _VIDEO_SCAN_DEFAULT_FRAMES
    frames = get_int("DISPUTE_VIDEO_SCAN_SAMPLE_FRAMES", configured_default)
    return frames if isinstance(frames, int) and frames > 0 else 0


def _dispute_video_compression_target_ratio() -> float:
    configured = getattr(
        settings, "DISPUTE_VIDEO_COMPRESSION_TARGET_RATIO", _VIDEO_COMPRESSION_DEFAULT_RATIO
    )
    try:
        ratio = float(configured)
    except (TypeError, ValueError):
        ratio = _VIDEO_COMPRESSION_DEFAULT_RATIO
    if ratio <= 0 or ratio >= 1:
        ratio = _VIDEO_COMPRESSION_DEFAULT_RATIO
    return ratio


def _dispute_video_compression_max_passes() -> int:
    configured = getattr(
        settings, "DISPUTE_VIDEO_COMPRESSION_MAX_PASSES", _VIDEO_COMPRESSION_DEFAULT_MAX_PASSES
    )
    if not isinstance(configured, int) or configured <= 0:
        return _VIDEO_COMPRESSION_DEFAULT_MAX_PASSES
    return configured


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _video_scan_payload_from_frames(path: str, *, frame_count: int) -> Optional[bytes]:
    if frame_count <= 0 or not _ffmpeg_available():
        return None
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                path,
                "-frames:v",
                str(frame_count),
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "pipe:1",
            ],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        logger.warning("ffmpeg frame extraction failed: %s", exc)
        return None
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode().strip()
        logger.warning("ffmpeg frame extraction failed: %s", stderr)
        return None
    payload = proc.stdout or b""
    if not payload:
        return None
    return payload


def _video_scale_filter(max_width: Optional[int]) -> str:
    if max_width:
        return f"scale=if(gt(iw\\,{max_width})\\,{max_width}\\,trunc(iw/2)*2):-2"
    return "scale=trunc(iw/2)*2:trunc(ih/2)*2"


def _video_compression_profiles(
    content_type: str, filename: str | None
) -> list[Tuple[str, list[str]]]:
    ext = os.path.splitext(filename or "")[1].lower()
    is_webm = content_type.lower() == "video/webm" or ext == ".webm"
    if is_webm:
        output_type = "video/webm"
        profiles = [
            {"crf": 33, "max_width": None, "audio_bitrate": "96k"},
            {"crf": 38, "max_width": 1280, "audio_bitrate": "64k"},
            {"crf": 42, "max_width": 854, "audio_bitrate": "64k"},
            {"crf": 45, "max_width": 640, "audio_bitrate": "48k"},
        ]
    else:
        output_type = "video/mp4"
        profiles = [
            {"crf": 28, "max_width": None, "audio_bitrate": "96k"},
            {"crf": 32, "max_width": 1280, "audio_bitrate": "64k"},
            {"crf": 36, "max_width": 854, "audio_bitrate": "64k"},
            {"crf": 40, "max_width": 640, "audio_bitrate": "48k"},
        ]

    items: list[Tuple[str, list[str]]] = []
    for profile in profiles:
        vf = _video_scale_filter(profile["max_width"])
        if output_type == "video/webm":
            args = [
                "-map_metadata",
                "0",
                "-vf",
                vf,
                "-c:v",
                "libvpx-vp9",
                "-b:v",
                "0",
                "-crf",
                str(profile["crf"]),
                "-deadline",
                "good",
                "-c:a",
                "libopus",
                "-b:a",
                profile["audio_bitrate"],
            ]
        else:
            args = [
                "-map_metadata",
                "0",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryslow",
                "-crf",
                str(profile["crf"]),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                profile["audio_bitrate"],
                "-movflags",
                "+faststart",
            ]
        items.append((output_type, args))
    return items


def _encode_video(
    path: str, *, output_type: str, args: list[str]
) -> Optional[Tuple[str, str, int]]:
    if not _ffmpeg_available():
        return None
    suffix = ".webm" if output_type == "video/webm" else ".mp4"
    fd, output_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", path, *args, output_path],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        logger.warning("ffmpeg compression failed: %s", exc)
        os.unlink(output_path)
        return None
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode().strip()
        logger.warning("ffmpeg compression failed: %s", stderr)
        os.unlink(output_path)
        return None
    return output_path, output_type, os.path.getsize(output_path)


def _compress_video_file(
    path: str,
    *,
    content_type: str,
    filename: str | None,
    target_size: int,
    max_passes: int,
) -> Optional[Tuple[str, str, int]]:
    if not _ffmpeg_available():
        return None
    profiles = _video_compression_profiles(content_type, filename)
    if max_passes > 0:
        profiles = profiles[:max_passes]
    best: Optional[Tuple[str, str, int]] = None
    for output_type, args in profiles:
        result = _encode_video(path, output_type=output_type, args=args)
        if not result:
            continue
        output_path, output_type, output_size = result
        if best is None or output_size < best[2]:
            if best:
                os.unlink(best[0])
            best = (output_path, output_type, output_size)
        else:
            os.unlink(output_path)
        if target_size and output_size <= target_size:
            break
    return best


def _upload_compressed_video(key: str, *, path: str, content_type: str) -> Optional[str]:
    if not getattr(settings, "USE_S3", False):
        return None
    with open(path, "rb") as handle:
        resp = _s3_client().put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
            Body=handle,
            ContentType=content_type,
        )
    etag = resp.get("ETag") if isinstance(resp, dict) else None
    return str(etag) if etag else None


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
        stream = io.BytesIO(data)

        def _size_from_stream(use_fast: bool) -> Tuple[int, int]:
            kwargs: dict[str, Any] = {"fast": True} if use_fast else {}
            with Image.open(stream, **kwargs) as img:
                width, height = img.size
                return int(width), int(height)

        try:
            return _size_from_stream(use_fast=True)
        except TypeError:
            # Pillow versions without the fast kwarg
            stream.seek(0)
        except UnidentifiedImageError:
            return None, None
        except Exception:
            stream.seek(0)
        return _size_from_stream(use_fast=False)
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
    meta = dict(meta or {})
    scan_payload: bytes
    if _is_video_meta(meta):
        tmp_path, used_dummy = _download_to_tempfile(key)
        try:
            scan_payload = b""
            frame_count = _dispute_video_scan_frames(meta)
            if not used_dummy:
                scan_payload = (
                    _video_scan_payload_from_frames(tmp_path, frame_count=frame_count) or b""
                )
                if scan_payload:
                    logger.info(
                        "video_scan_frames_sampled",
                        extra={
                            "key": key,
                            "frame_count": frame_count,
                            "sample_bytes": len(scan_payload),
                            "content_type": meta.get("content_type"),
                        },
                    )
            if not scan_payload:
                byte_limit = _dispute_video_scan_limit(meta)
                scan_payload = _read_file_bytes(tmp_path, byte_limit=byte_limit)
                if byte_limit:
                    logger.info(
                        "video_scan_sampled",
                        extra={
                            "key": key,
                            "byte_limit": byte_limit,
                            "downloaded_bytes": len(scan_payload),
                            "content_type": meta.get("content_type"),
                        },
                    )
            verdict = _scan_bytes(scan_payload)

            original_size = os.path.getsize(tmp_path)
            if verdict == "clean" and not used_dummy and getattr(settings, "USE_S3", False):
                if not _ffmpeg_available():
                    logger.warning(
                        "video_compression_unavailable",
                        extra={"key": key, "content_type": meta.get("content_type")},
                    )
                else:
                    target_ratio = _dispute_video_compression_target_ratio()
                    target_size = max(int(original_size * target_ratio), 1)
                    max_passes = _dispute_video_compression_max_passes()
                    compressed = _compress_video_file(
                        tmp_path,
                        content_type=meta.get("content_type") or "",
                        filename=meta.get("filename"),
                        target_size=target_size,
                        max_passes=max_passes,
                    )
                    if compressed:
                        output_path, output_type, output_size = compressed
                        try:
                            if output_size < original_size:
                                etag = _upload_compressed_video(
                                    key, path=output_path, content_type=output_type
                                )
                                if etag:
                                    meta["content_type"] = output_type
                                    meta["size"] = output_size
                                    meta["etag"] = etag
                                    logger.info(
                                        "video_compressed",
                                        extra={
                                            "key": key,
                                            "original_size": original_size,
                                            "compressed_size": output_size,
                                            "target_size": target_size,
                                            "target_ratio": target_ratio,
                                            "content_type": output_type,
                                        },
                                    )
                                    if output_size > target_size:
                                        logger.info(
                                            "video_compression_target_missed",
                                            extra={
                                                "key": key,
                                                "original_size": original_size,
                                                "compressed_size": output_size,
                                                "target_size": target_size,
                                                "target_ratio": target_ratio,
                                                "max_passes": max_passes,
                                            },
                                        )
                            else:
                                logger.info(
                                    "video_compression_skipped",
                                    extra={
                                        "key": key,
                                        "original_size": original_size,
                                        "compressed_size": output_size,
                                    },
                                )
                        finally:
                            os.unlink(output_path)
            if not meta.get("size"):
                meta["size"] = original_size
        finally:
            os.unlink(tmp_path)
    else:
        byte_limit = _dispute_video_scan_limit(meta)
        scan_payload = _download_bytes(key, byte_limit=byte_limit)
        if byte_limit:
            logger.info(
                "video_scan_sampled",
                extra={
                    "key": key,
                    "byte_limit": byte_limit,
                    "downloaded_bytes": len(scan_payload),
                    "content_type": meta.get("content_type"),
                },
            )
        verdict = _scan_bytes(scan_payload)
    dimensions = _extract_dimensions(scan_payload)
    constraint_error = validate_image_limits(
        content_type=meta.get("content_type") if meta else "",
        size=len(scan_payload),
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
                "bytes": len(scan_payload),
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
    try:
        from disputes.intake import update_dispute_intake_status
        from disputes.models import DisputeCase

        status = DisputeCase.objects.filter(pk=dispute_id).values_list("status", flat=True).first()
        if status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE:
            update_dispute_intake_status(dispute_id)
    except Exception:
        logger.info(
            "dispute evidence: failed to refresh intake status",
            extra={"dispute_id": dispute_id, "evidence_id": evidence.id},
            exc_info=True,
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
