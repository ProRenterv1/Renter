from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from storage.s3 import guess_content_type, object_key, presign_put
from storage.tasks import scan_and_finalize_photo

from .models import Listing
from .serializers import ListingPhotoSerializer, ListingSerializer
from .services import search_listings


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
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsOwnerOrReadOnly,
        CanListItems,
    ]
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        q = params.get("q")
        category = params.get("category")
        city = params.get("city")
        pmin_raw = params.get("price_min")
        pmax_raw = params.get("price_max")
        try:
            pmin = float(pmin_raw) if pmin_raw not in (None, "") else None
        except (TypeError, ValueError):
            pmin = None
        try:
            pmax = float(pmax_raw) if pmax_raw not in (None, "") else None
        except (TypeError, ValueError):
            pmax = None
        return search_listings(qs, q, pmin, pmax, category=category, city=city)

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


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def photos_presign(request, listing_id: int):
    listing = get_object_or_404(Listing, id=listing_id, owner_id=request.user.id)
    filename = request.data.get("filename") or "upload"
    content_type = request.data.get("content_type") or guess_content_type(filename)
    content_md5 = request.data.get("content_md5")
    size = request.data.get("size")
    try:
        size_hint = int(size) if size not in (None, "") else None
    except (TypeError, ValueError):
        return Response({"detail": "size must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

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
    get_object_or_404(Listing, id=listing_id, owner_id=request.user.id)
    key = request.data.get("key")
    etag = request.data.get("etag")
    if not key or not etag:
        return Response({"detail": "key and etag required"}, status=status.HTTP_400_BAD_REQUEST)

    scan_and_finalize_photo.delay(
        key=key,
        listing_id=listing_id,
        owner_id=request.user.id,
        meta={
            "etag": etag,
            "filename": request.data.get("filename") or "upload",
            "content_type": request.data.get("content_type"),
            "size": request.data.get("size"),
        },
    )
    return Response({"status": "queued", "key": key})
