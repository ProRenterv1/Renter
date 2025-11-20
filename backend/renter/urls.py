from django.contrib import admin
from django.urls import include, path

from core.health import healthz
from views_events import events_stream

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/healthz", healthz),
    path("api/events/stream/", events_stream, name="events_stream"),
    path("api/users/", include("users.urls")),
    path("api/listings/", include("listings.urls")),
    path("api/bookings/", include(("bookings.urls", "bookings"), namespace="bookings")),
    path("api/payments/", include("payments.urls")),
    path("api/owner/payouts/", include("payments.urls_owner_payouts")),
    path("api/", include("chat.urls")),
]
