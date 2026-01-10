from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from core.health import healthz
from core.maintenance import maintenance_status
from core.pricing import pricing_summary
from views_events import events_stream

urlpatterns = [
    path("api/healthz", healthz),
    path("api/events/stream/", events_stream, name="events_stream"),
    path("api/maintenance/", maintenance_status, name="maintenance_status"),
    path("api/platform/pricing/", pricing_summary, name="pricing_summary"),
    path("api/users/", include("users.urls")),
    path("api/listings/", include("listings.urls")),
    path("api/bookings/", include(("bookings.urls", "bookings"), namespace="bookings")),
    path("api/payments/", include("payments.urls")),
    path("api/owner/payouts/", include("payments.urls_owner_payouts")),
    path("api/disputes/", include("disputes.urls")),
    path("api/promotions/", include("promotions.urls")),
    path("api/identity/", include("identity.urls")),
    path("api/reviews/", include("reviews.urls")),
    path("api/", include("chat.urls")),
]

if settings.ENABLE_DJANGO_ADMIN:
    urlpatterns.insert(0, path("admin/", admin.site.urls))

if settings.ENABLE_OPERATOR:
    urlpatterns.append(path("api/operator/", include("operator_core.urls")))
