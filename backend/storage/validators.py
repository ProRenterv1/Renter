from __future__ import annotations

from typing import Optional

from django.conf import settings


def is_image_content_type(content_type: str) -> bool:
    return (content_type or "").lower().startswith("image/")


def coerce_int(value) -> Optional[int]:
    if value in (None, "", False):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def max_bytes_for_content_type(content_type: str) -> Optional[int]:
    global_limit = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
    if is_image_content_type(content_type):
        image_limit = getattr(settings, "IMAGE_MAX_UPLOAD_BYTES", None)
        if image_limit and global_limit:
            return min(image_limit, global_limit)
        return image_limit or global_limit
    return global_limit


def validate_image_limits(
    *,
    content_type: str,
    size: Optional[int],
    width: Optional[int],
    height: Optional[int],
) -> Optional[str]:
    if not is_image_content_type(content_type):
        return None

    max_bytes = getattr(settings, "IMAGE_MAX_UPLOAD_BYTES", None)
    if max_bytes and size is not None and size > max_bytes:
        return f"Image too large. Max allowed is {max_bytes} bytes."

    max_dim = getattr(settings, "IMAGE_MAX_DIMENSION", None)
    if max_dim:
        if width and width > max_dim:
            return f"Image width exceeds the dimension limit of {max_dim}px."
        if height and height > max_dim:
            return f"Image height exceeds the dimension limit of {max_dim}px."

    return None
