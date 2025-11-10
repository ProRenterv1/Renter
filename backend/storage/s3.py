import mimetypes
import uuid
from datetime import timedelta
from typing import Dict, Optional

import boto3
from botocore.config import Config
from django.conf import settings


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
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    uid = uuid.uuid4().hex
    safe = f"{uid}.{ext}" if ext else uid
    return f"{settings.S3_UPLOADS_PREFIX}/l{listing_id}/u{owner_id}/{safe}"


def presign_put(
    key: str,
    *,
    content_type: str,
    content_md5: Optional[str] = None,
    size_hint: Optional[int] = None,
) -> Dict:
    if size_hint and size_hint > settings.S3_MAX_UPLOAD_BYTES:
        raise ValueError("File too large")
    params = {"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": key, "ContentType": content_type}
    headers = {"Content-Type": content_type, "x-amz-tagging": "av-status=pending"}
    if content_md5:
        params["ContentMD5"] = content_md5
        headers["Content-MD5"] = content_md5
    url = _client().generate_presigned_url(
        ClientMethod="put_object",
        Params={**params, "Tagging": "av-status=pending"},
        ExpiresIn=int(timedelta(minutes=10).total_seconds()),
    )
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
