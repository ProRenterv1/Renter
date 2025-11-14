import mimetypes
import os
import uuid
from typing import Dict, Optional

import boto3
from botocore.config import Config
from django.conf import settings
from django.utils.text import slugify


def _client():
    cfg = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if settings.AWS_S3_FORCE_PATH_STYLE else "auto"},
    )
    return boto3.client(
        "s3",
        region_name=settings.AWS_S3_REGION_NAME,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
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


def presign_put(
    key: str,
    *,
    content_type: str,
    content_md5: Optional[str] = None,
    size_hint: Optional[int] = None,
) -> Dict:
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
    _client().put_object_tagging(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]},
    )


def set_metadata_copy(key: str, new_metadata: Dict[str, str]):
    c = _client()
    c.copy_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        CopySource={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": key},
        Metadata=new_metadata,
        MetadataDirective="REPLACE",
    )


def public_url(key: str) -> str:
    endpoint = settings.AWS_S3_ENDPOINT_URL
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    if endpoint and "localhost" in endpoint:
        return f"{endpoint}/{bucket}/{key}"
    return f"https://{bucket}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{key}"


def guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
