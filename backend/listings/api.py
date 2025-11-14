from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from storage.s3 import guess_content_type, object_key, presign_put, public_url
from storage.tasks import scan_and_finalize_photo

from .models import Category, Listing, ListingPhoto
from .serializers import CategorySerializer, ListingPhotoSerializer, ListingSerializer
from .services import search_listings


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
    queryset = Listing.objects.all().select_related("owner", "category").prefetch_related("photos")
    serializer_class = ListingSerializer
    pagination_class = ListingPagination
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsOwnerOrReadOnly,
        CanListItems,
    ]
    lookup_field = "slug"

    def get_permissions(self):
        if self.action in {"list", "retrieve", "photos_list"}:
            return [permissions.AllowAny()]
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        base_qs = Listing.objects.select_related("owner", "category").prefetch_related("photos")
        params = self.request.query_params
        q = params.get("q") or None
        category = params.get("category") or None
        city = params.get("city") or None

        price_min_raw = params.get("price_min")
        price_max_raw = params.get("price_max")

        try:
            price_min = float(price_min_raw) if price_min_raw not in (None, "") else None
        except (TypeError, ValueError):
            price_min = None
        try:
            price_max = float(price_max_raw) if price_max_raw not in (None, "") else None
        except (TypeError, ValueError):
            price_max = None

        return search_listings(
            qs=base_qs,
            q=q,
            price_min=price_min,
            price_max=price_max,
            category=category,
            city=city,
        )

    def perform_create(self, serializer):
        serializer.save()

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


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


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
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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
