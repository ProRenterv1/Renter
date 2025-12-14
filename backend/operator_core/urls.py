from django.urls import include, path

from operator_core.api import OperatorAuditTestMutation, OperatorMeView
from operator_core.dashboard_api import OperatorDashboardView

urlpatterns = [
    path("me/", OperatorMeView.as_view(), name="operator_me"),
    path("audit-test/", OperatorAuditTestMutation.as_view(), name="operator_audit_test"),
    path("dashboard/", OperatorDashboardView.as_view(), name="operator_dashboard"),
    path("users/", include("operator_users.urls")),
]
