from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import CategoryViewSet, ListingViewSet, photos_complete, photos_presign

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("", ListingViewSet, basename="listing")

urlpatterns = [
    path(
        "<int:listing_id>/photos/presign",
        photos_presign,
        name="photos_presign",
    ),
    path(
        "<int:listing_id>/photos/complete",
        photos_complete,
        name="photos_complete",
    ),
    path("", include(router.urls)),
]
