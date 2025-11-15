"""URL routing for the bookings API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import BookingViewSet

app_name = "bookings"

router = DefaultRouter()
router.register("", BookingViewSet, basename="booking")

urlpatterns = [
    path("", include(router.urls)),
]
