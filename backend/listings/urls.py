from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import ListingViewSet

router = DefaultRouter()
router.register("", ListingViewSet, basename="listing")

urlpatterns = [
    path("", include(router.urls)),
]
