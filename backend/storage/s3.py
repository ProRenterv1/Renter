import mimetypes
import os
import uuid
from typing import Dict, Optional

import boto3
from botocore.config import Config
from django.conf import settings
from django.utils.text import slugify


def _normalized_endpoint(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def _client():
    addressing_style = "path" if getattr(settings, "AWS_S3_FORCE_PATH_STYLE", False) else "auto"
    cfg = Config(
        signature_version="s3v4",
        s3={"addressing_style": addressing_style},
    )
    endpoint = _normalized_endpoint(getattr(settings, "AWS_S3_ENDPOINT_URL", None))
    return boto3.client(
        "s3",
        region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
        endpoint_url=endpoint,
        config=cfg,
    )


def object_key(listing_id: int, owner_id: int, filename: str) -> str:
    prefix = (getattr(settings, "S3_UPLOADS_PREFIX", "") or "").strip("/")
    name, ext = os.path.splitext(filename or "")
    safe_name = slugify(name) or "upload"
    ext = ext.lower().lstrip(".")
    unique_prefix = str(uuid.uuid4())
    combined_name = f"{unique_prefix}-{safe_name}"
    if ext:
        combined_name = f"{combined_name}.{ext}"
    parts = [prefix, "listings", str(listing_id), str(owner_id), combined_name]
    return "/".join(part for part in parts if part)


def booking_object_key(booking_id: int, user_id: int, filename: str) -> str:
    prefix = (getattr(settings, "S3_UPLOADS_PREFIX", "") or "").strip("/")
    name, ext = os.path.splitext(filename or "")
    safe_name = slugify(name) or "upload"
    ext = ext.lower().lstrip(".")
    unique_prefix = str(uuid.uuid4())
    combined_name = f"{unique_prefix}-{safe_name}"
    if ext:
        combined_name = f"{combined_name}.{ext}"
    parts = [prefix, "bookings", str(booking_id), str(user_id), combined_name]
    return "/".join(part for part in parts if part)


def presign_put(
    key: str,
    *,
    content_type: str,
    content_md5: Optional[str] = None,
    size_hint: Optional[int] = None,
) -> Dict:
    if not getattr(settings, "USE_S3", False):
        # In local/test environments without S3, return a dummy presign target.
        headers = {"Content-Type": content_type}
        if content_md5:
            headers["Content-MD5"] = content_md5
        return {
            "upload_url": f"http://example.com/mock-upload/{key}",
            "headers": headers,
        }

    max_size = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
    if size_hint is not None and max_size is not None and size_hint > max_size:
        raise ValueError("Upload exceeds the maximum allowed size.")

    params = {
        "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
        "Key": key,
        "ContentType": content_type,
    }
    if content_md5:
        params["ContentMD5"] = content_md5

    url = _client().generate_presigned_url(
        ClientMethod="put_object",
        Params=params,
        ExpiresIn=900,
    )

    headers = {"Content-Type": content_type}
    if content_md5:
        headers["Content-MD5"] = content_md5

    return {"upload_url": url, "headers": headers}


def head_object(key: str) -> Dict:
    return _client().head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)


def tag_object(key: str, tags: Dict[str, str]):
    if not getattr(settings, "USE_S3", False):
        return
    _client().put_object_tagging(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]},
    )


def set_metadata_copy(key: str, new_metadata: Dict[str, str]):
    if not getattr(settings, "USE_S3", False):
        return
    c = _client()
    c.copy_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        CopySource={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": key},
        Metadata=new_metadata,
        MetadataDirective="REPLACE",
    )


def public_url(key: str) -> str:
    def _join(base: str, suffix: str) -> str:
        return f"{base.rstrip('/')}/{suffix.lstrip('/')}"

    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    public_base = (getattr(settings, "S3_PUBLIC_BASE_URL", "") or "").strip()
    media_base = (getattr(settings, "MEDIA_BASE_URL", "") or "").strip()
    endpoint = (getattr(settings, "AWS_S3_ENDPOINT_URL", "") or "").strip()
    region = getattr(settings, "AWS_S3_REGION_NAME", "") or ""

    if public_base:
        normalized = _normalized_endpoint(public_base) or public_base
        return _join(normalized, key)
    if media_base:
        normalized = _normalized_endpoint(media_base) or media_base
        return _join(normalized, key)
    if endpoint:
        normalized = _normalized_endpoint(endpoint) or endpoint
        return _join(f"{normalized}/{bucket}", key)
    if region and region != "auto":
        return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    return f"https://{bucket}.s3.amazonaws.com/{key}"


def guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def presign_get(
    key: str, *, expires_in: int = 600, response_content_type: Optional[str] = None
) -> Dict:
    """
    Return a presigned GET URL for the given object key.
    """
    if not getattr(settings, "USE_S3", False):
        url = f"http://example.com/mock-download/{key}"
        return {"url": url, "headers": {}}

    params = {
        "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
        "Key": key,
    }
    if response_content_type:
        params["ResponseContentType"] = response_content_type

    url = _client().generate_presigned_url(
        ClientMethod="get_object",
        Params=params,
        ExpiresIn=expires_in,
    )
    return {"url": url, "headers": {}}
