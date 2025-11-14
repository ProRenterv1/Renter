from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from .api import CategoryViewSet, ListingViewSet, photos_complete, photos_presign

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("", ListingViewSet, basename="listing")

urlpatterns = [
    re_path(
        r"^(?P<listing_id>\d+)/photos/presign/?$",
        photos_presign,
        name="photos_presign",
    ),
    re_path(
        r"^(?P<listing_id>\d+)/photos/complete/?$",
        photos_complete,
        name="photos_complete",
    ),
    path("", include(router.urls)),
]
