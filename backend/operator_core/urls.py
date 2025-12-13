from django.urls import path

from operator_core.api import OperatorAuditTestMutation, OperatorMeView

urlpatterns = [
    path("me/", OperatorMeView.as_view(), name="operator_me"),
    path("audit-test/", OperatorAuditTestMutation.as_view(), name="operator_audit_test"),
]
