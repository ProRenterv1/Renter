from __future__ import annotations

import io
import subprocess
from typing import Tuple

import boto3
from celery import shared_task
from django.conf import settings
from django.db import transaction

from . import s3 as s3util


def _download_bytes(key: str) -> bytes:
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        region_name=settings.AWS_S3_REGION_NAME,
    )
    obj = s3.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
    return obj["Body"].read()


def _scan_bytes(data: bytes) -> Tuple[bool, str]:
    engine = getattr(settings, "AV_ENGINE", "clamd")
    if engine == "dummy":
        marker = getattr(settings, "AV_DUMMY_INFECT_MARKER", "").encode()
        return (marker not in data, "dummy")
    if engine == "clamscan":
        proc = subprocess.run(
            ["clamscan", "--no-summary", "-"],
            input=data,
            capture_output=True,
            check=False,
        )
        output = (proc.stdout or b"").decode().strip()
        return (proc.returncode == 0, output)

    try:
        import clamd

        cd = clamd.ClamdUnixSocket()
        resp = cd.instream(io.BytesIO(data))
        stream = resp.get("stream", {})
        return (stream.get("status") == "OK", str(resp))
    except Exception as exc:
        return (False, f"clamd-error:{exc}")


def _coerce_size(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _apply_av_metadata(key: str, is_clean: bool) -> None:
    status = "clean" if is_clean else "infected"
    s3util.tag_object(key, {"av-status": status})
    try:
        s3util.set_metadata_copy(key, {"x-av": status})
    except Exception:
        # We don't want tagging failures to block the upload flow.
        pass


def scan_and_finalize_photo(
    *,
    key: str,
    listing_id: int,
    owner_id: int,
    meta: dict | None = None,
):
    """
    Core implementation reused by both Celery and direct (synchronous) callers.
    """

    from listings.models import Listing, ListingPhoto

    meta = meta or {}
    blob = _download_bytes(key)
    is_clean, _msg = _scan_bytes(blob)
    _apply_av_metadata(key, is_clean)

    with transaction.atomic():
        Listing.objects.select_for_update().get(id=listing_id, owner_id=owner_id)
        if is_clean:
            photo = ListingPhoto.objects.create(
                listing_id=listing_id,
                owner_id=owner_id,
                key=key,
                url=s3util.public_url(key),
                status=ListingPhoto.Status.ACTIVE,
                content_type=meta.get("content_type") or "",
                size=_coerce_size(meta.get("size")),
                etag=(meta.get("etag") or "").strip('"'),
                av_status=ListingPhoto.AVStatus.CLEAN,
                filename=meta.get("filename") or "",
            )
            return {"status": "clean", "photo_id": str(photo.id)}
        return {"status": "infected"}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="storage.tasks.scan_and_finalize_photo",
)
def scan_and_finalize_photo_task(
    self,
    *,
    key: str,
    listing_id: int,
    owner_id: int,
    meta: dict | None = None,
):
    try:
        return scan_and_finalize_photo(
            key=key,
            listing_id=listing_id,
            owner_id=owner_id,
            meta=meta,
        )
    except Exception as exc:  # pragma: no cover - retries exercised in Celery
        raise self.retry(exc=exc)


# Preserve the previous API where callers could import scan_and_finalize_photo
# and call .delay() on it.
def _delay_wrapper(**kwargs):
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        if getattr(settings, "STORAGE_SKIP_TASK_EXECUTION", False):
            return None
        return scan_and_finalize_photo(**kwargs)
    return scan_and_finalize_photo_task.delay(**kwargs)


scan_and_finalize_photo.delay = _delay_wrapper  # type: ignore[attr-defined]
scan_and_finalize_photo.apply_async = scan_and_finalize_photo_task.apply_async

__all__ = ["scan_and_finalize_photo", "scan_and_finalize_photo_task"]
