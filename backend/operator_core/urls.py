from django.urls import include, path

from operator_core.api import OperatorAuditTestMutation, OperatorMeView, OperatorNotesView
from operator_core.dashboard_api import OperatorDashboardView
from operator_core.health_api import OperatorHealthTestEmailView, OperatorHealthView

urlpatterns = [
    path("me/", OperatorMeView.as_view(), name="operator_me"),
    path("audit-test/", OperatorAuditTestMutation.as_view(), name="operator_audit_test"),
    path("dashboard/", OperatorDashboardView.as_view(), name="operator_dashboard"),
    path("health/", OperatorHealthView.as_view(), name="operator_health"),
    path(
        "health/test-email/",
        OperatorHealthTestEmailView.as_view(),
        name="operator_health_test_email",
    ),
    path("notes/", OperatorNotesView.as_view(), name="operator_notes"),
    path("", include("operator_settings.urls")),
    path("", include("operator_finance.urls")),
    path("listings/", include("operator_listings.urls")),
    path("bookings/", include("operator_bookings.urls")),
    path("users/", include("operator_users.urls")),
]
