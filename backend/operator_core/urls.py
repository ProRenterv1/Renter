from django.urls import include, path

from operator_core.api import OperatorAuditTestMutation, OperatorMeView, OperatorNotesView
from operator_core.dashboard_api import OperatorDashboardView

urlpatterns = [
    path("me/", OperatorMeView.as_view(), name="operator_me"),
    path("audit-test/", OperatorAuditTestMutation.as_view(), name="operator_audit_test"),
    path("dashboard/", OperatorDashboardView.as_view(), name="operator_dashboard"),
    path("notes/", OperatorNotesView.as_view(), name="operator_notes"),
    path("", include("operator_finance.urls")),
    path("listings/", include("operator_listings.urls")),
    path("bookings/", include("operator_bookings.urls")),
    path("users/", include("operator_users.urls")),
]
