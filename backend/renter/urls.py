from django.contrib import admin
from django.urls import path
from core.health import healthz
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/healthz", healthz),
]