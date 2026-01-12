from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import PublicReviewListView, ReviewViewSet

router = DefaultRouter()
router.register("", ReviewViewSet, basename="review")

urlpatterns = [
    path("public/", PublicReviewListView.as_view(), name="public_reviews"),
    path("", include(router.urls)),
]
