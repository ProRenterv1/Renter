import json
import logging
from functools import lru_cache

import redis
import requests
from django.conf import settings
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from promotions.models import PromotedSlot
from storage.s3 import guess_content_type, object_key, presign_put, public_url
from storage.tasks import scan_and_finalize_photo

from .models import Category, Listing, ListingPhoto
from .serializers import CategorySerializer, ListingPhotoSerializer, ListingSerializer
from .services import search_listings

logger = logging.getLogger(__name__)

GEOCODE_ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
GEOCODE_CACHE_PREFIX = "listings:geocode:"


class GeocodeServiceError(Exception):
    """Raised when the external geocode service fails."""


class GeocodeNotFoundError(Exception):
    """Raised when no coordinates are returned for an address."""


@lru_cache(maxsize=1)
def get_redis_client():
    return redis.Redis.from_url(settings.REDIS_URL)


def _normalize_component(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_postal_code(value: str) -> str:
    normalized = _normalize_component(value)
    return normalized.upper()


def _postal_fingerprint(value: str) -> str:
    return "".join(value.split()).upper()


def _fingerprint(value: str) -> str:
    return _normalize_component(value).lower()


def _cache_key(postal_code: str, city: str, region: str) -> str:
    parts = [
        _postal_fingerprint(postal_code),
        _fingerprint(city),
        _fingerprint(region),
    ]
    return f"{GEOCODE_CACHE_PREFIX}{'|'.join(parts)}"


def _load_cached_geocode(cache_key: str):
    try:
        cached = get_redis_client().get(cache_key)
    except redis.RedisError as exc:
        logger.warning("Failed to read geocode cache", exc_info=exc)
        return None
    if not cached:
        return None
    try:
        if isinstance(cached, bytes):
            cached_str = cached.decode("utf-8")
        else:
            cached_str = cached
        return json.loads(cached_str)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Failed to decode cached geocode payload", exc_info=exc)
        return None


def _store_cached_geocode(cache_key: str, payload: dict) -> None:
    ttl = getattr(settings, "GEOCODE_CACHE_TTL", 24 * 60 * 60)
    try:
        get_redis_client().setex(cache_key, ttl, json.dumps(payload))
    except redis.RedisError as exc:
        logger.warning("Failed to write geocode cache", exc_info=exc)


def _request_geocode(address: str, api_key: str):
    try:
        response = requests.get(
            GEOCODE_ENDPOINT,
            params={
                "address": address,
                "key": api_key,
            },
            timeout=getattr(settings, "GEOCODE_REQUEST_TIMEOUT", 5.0),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodeServiceError("Geocoding request failed") from exc

    payload = response.json()
    status_value = payload.get("status")
    if status_value == "ZERO_RESULTS":
        raise GeocodeNotFoundError("No results for address")
    if status_value != "OK":
        logger.warning(
            "Google Geocoding returned error", extra={"status": status_value, "address": address}
        )
        raise GeocodeServiceError(f"Geocoding service error: {status_value}")

    results = payload.get("results") or []
    if not results:
        raise GeocodeServiceError("Geocoding response missing results")

    geometry = results[0].get("geometry") or {}
    location = geometry.get("location") or {}
    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        raise GeocodeServiceError("Geocoding response missing coordinates")

    formatted_address = results[0].get("formatted_address") or address
    return formatted_address, float(lat), float(lng)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def geocode_listing_location(request):
    postal_code_raw = (request.query_params.get("postal_code") or "").strip()
    city_raw = (request.query_params.get("city") or "").strip()
    region_raw = (request.query_params.get("region") or "").strip()

    if not postal_code_raw:
        return Response(
            {"detail": "postal_code is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None)
    if not api_key:
        return Response(
            {"detail": "Geocoding is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    sanitized_postal_code = _normalize_postal_code(postal_code_raw)
    sanitized_city = _normalize_component(city_raw)
    sanitized_region = _normalize_component(region_raw)

    cache_key = _cache_key(sanitized_postal_code, sanitized_city, sanitized_region)
    cached_payload = _load_cached_geocode(cache_key)
    if cached_payload:
        response_payload = dict(cached_payload)
        response_payload["cache_hit"] = True
        return Response(response_payload)

    address_parts = [sanitized_postal_code]
    if sanitized_city:
        address_parts.append(sanitized_city)
    if sanitized_region:
        address_parts.append(sanitized_region)
    address_str = ", ".join(address_parts)

    try:
        formatted_address, lat, lng = _request_geocode(address_str, api_key)
    except GeocodeNotFoundError:
        return Response(
            {"detail": "Location not found for the provided address."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except GeocodeServiceError:
        return Response(
            {"detail": "Unable to fetch location details at this time."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    payload = {
        "location": {"lat": lat, "lng": lng},
        "formatted_address": formatted_address,
        "address": {
            "postal_code": sanitized_postal_code,
            "city": sanitized_city or None,
            "region": sanitized_region or None,
        },
    }
    _store_cached_geocode(cache_key, payload)
    response_payload = dict(payload)
    response_payload["cache_hit"] = False
    return Response(response_payload)


class ListingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(obj, "owner_id", None) == getattr(request.user, "id", None)


class CanListItems(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method == "POST":
            user = request.user
            return bool(user and user.is_authenticated and getattr(user, "can_list", False))
        return True


class ListingViewSet(viewsets.ModelViewSet):
    queryset = (
        Listing.objects.filter(is_deleted=False)
        .select_related("owner", "category")
        .prefetch_related("photos")
    )
    serializer_class = ListingSerializer
    pagination_class = ListingPagination
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsOwnerOrReadOnly,
        CanListItems,
    ]
    lookup_field = "slug"

    def get_permissions(self):
        if getattr(self, "action", None) in {"list", "retrieve", "photos_list"}:
            return [permissions.AllowAny()]
        return [permission() for permission in self.permission_classes]

    def perform_authentication(self, request):
        """Downgrade to anonymous user when public actions receive invalid tokens."""
        try:
            return super().perform_authentication(request)
        except AuthenticationFailed:
            if getattr(self, "action", None) in {"list", "retrieve", "photos_list"}:
                request._not_authenticated()
                return
            raise

    def get_queryset(self):
        base_qs = (
            Listing.objects.filter(is_deleted=False)
            .select_related("owner", "category")
            .prefetch_related("photos")
        )
        params = self.request.query_params
        q = params.get("q") or None
        category = params.get("category") or None
        city = params.get("city") or None

        price_min_raw = params.get("price_min")
        price_max_raw = params.get("price_max")
        owner_id_raw = params.get("owner_id")

        try:
            price_min = float(price_min_raw) if price_min_raw not in (None, "") else None
        except (TypeError, ValueError):
            price_min = None
        try:
            price_max = float(price_max_raw) if price_max_raw not in (None, "") else None
        except (TypeError, ValueError):
            price_max = None
        try:
            owner_id = int(owner_id_raw) if owner_id_raw not in (None, "") else None
        except (TypeError, ValueError):
            owner_id = None

        qs = search_listings(
            qs=base_qs,
            q=q,
            price_min=price_min,
            price_max=price_max,
            category=category,
            city=city,
            owner_id=owner_id,
        )
        active_slots = PromotedSlot.active_for_feed().filter(listing_id=OuterRef("pk"))
        qs = qs.annotate(is_promoted=Exists(active_slots))
        return qs.order_by("-is_promoted", "-created_at")

    def perform_create(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)

        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        update_fields = ["is_deleted", "deleted_at"]
        if hasattr(instance, "updated_at"):
            update_fields.append("updated_at")
        instance.save(update_fields=update_fields)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="photos")
    def photos_list(self, request, slug=None):
        listing = self.get_object()
        serializer = ListingPhotoSerializer(listing.photos.all(), many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"photos/(?P<photo_id>[^/.]+)",
    )
    def photos_delete(self, request, slug=None, photo_id=None):
        listing = self.get_object()
        photo = listing.photos.filter(id=photo_id).first()
        if not photo:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if listing.owner_id != getattr(request.user, "id", None):
            return Response(status=status.HTTP_403_FORBIDDEN)
        photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=["get"],
        url_path="mine",
        permission_classes=[IsAuthenticated],
    )
    def mine(self, request):
        """Return the authenticated user's listings using existing pagination."""
        qs = (
            Listing.objects.filter(owner=request.user, is_deleted=False)
            .select_related("category")
            .prefetch_related("photos")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []


def _require_listing_owner(listing_id: int, user) -> Listing:
    listing = get_object_or_404(Listing, id=listing_id)
    if listing.owner_id != getattr(user, "id", None):
        raise PermissionDenied("Only the listing owner can manage photos.")
    return listing


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def photos_presign(request, listing_id: int):
    listing_id = int(listing_id)
    listing = _require_listing_owner(listing_id, request.user)
    filename = request.data.get("filename") or "upload"
    content_type = request.data.get("content_type") or guess_content_type(filename)
    content_md5 = request.data.get("content_md5")
    size_raw = request.data.get("size")
    if size_raw in (None, ""):
        return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        size_hint = int(size_raw)
    except (TypeError, ValueError):
        return Response({"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
    if size_hint <= 0:
        return Response(
            {"detail": "size must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST
        )
    max_bytes = settings.S3_MAX_UPLOAD_BYTES
    if max_bytes and size_hint > max_bytes:
        return Response(
            {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    key = object_key(listing_id=listing.id, owner_id=request.user.id, filename=filename)
    try:
        presigned = presign_put(
            key,
            content_type=content_type,
            content_md5=content_md5,
            size_hint=size_hint,
        )
    except ValueError:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {
            "key": key,
            "upload_url": presigned["upload_url"],
            "headers": presigned["headers"],
            "max_bytes": settings.S3_MAX_UPLOAD_BYTES,
            "tagging": "av-status=pending",
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def photos_complete(request, listing_id: int):
    listing_id = int(listing_id)
    listing = _require_listing_owner(listing_id, request.user)
    key = request.data.get("key")
    etag = request.data.get("etag")
    if not key or not etag:
        return Response({"detail": "key and etag required."}, status=status.HTTP_400_BAD_REQUEST)

    filename = request.data.get("filename") or "upload"
    content_type = request.data.get("content_type") or guess_content_type(filename)
    size_raw = request.data.get("size")
    if size_raw in (None, ""):
        return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        size_int = int(size_raw)
    except (TypeError, ValueError):
        return Response({"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
    if size_int <= 0:
        return Response(
            {"detail": "size must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST
        )
    max_bytes = settings.S3_MAX_UPLOAD_BYTES
    if max_bytes and size_int > max_bytes:
        return Response(
            {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    photo_url = public_url(key)
    photo, _ = ListingPhoto.objects.get_or_create(
        listing=listing,
        owner=request.user,
        key=key,
        defaults={"url": photo_url},
    )
    photo.url = photo_url
    photo.filename = filename
    photo.content_type = content_type
    photo.size = size_int
    photo.etag = (etag or "").strip('"')
    photo.status = ListingPhoto.Status.PENDING
    photo.av_status = ListingPhoto.AVStatus.PENDING
    photo.width = None
    photo.height = None
    photo.save()

    meta = {
        "etag": etag,
        "filename": filename,
        "content_type": content_type,
        "size": size_int,
    }
    scan_and_finalize_photo.delay(
        key=key,
        listing_id=listing_id,
        owner_id=request.user.id,
        meta=meta,
    )
    return Response({"status": "queued", "key": key}, status=status.HTTP_202_ACCEPTED)
