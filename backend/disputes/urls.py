from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import DisputeCaseViewSet

app_name = "disputes"

router = DefaultRouter()
router.register("", DisputeCaseViewSet, basename="dispute")

urlpatterns = [
    path("", include(router.urls)),
]
