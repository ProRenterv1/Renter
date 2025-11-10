from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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
    queryset = Listing.objects.all().select_related("owner").prefetch_related("photos")
    serializer_class = ListingSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsOwnerOrReadOnly,
        CanListItems,
    ]
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        pmin = self.request.query_params.get("price_min")
        pmax = self.request.query_params.get("price_max")
        pmin = float(pmin) if pmin not in (None, "") else None
        pmax = float(pmax) if pmax not in (None, "") else None
        return search_listings(qs, q, pmin, pmax)

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
