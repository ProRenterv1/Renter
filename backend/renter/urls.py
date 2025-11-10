from django.contrib import admin
from django.urls import include, path

from core.health import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/healthz", healthz),
    path("api/users/", include("users.urls")),
    path("api/listings/", include("listings.urls")),
]
