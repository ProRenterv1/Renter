from django.urls import path

from operator_disputes.api import (
    OperatorDisputeCloseDuplicateView,
    OperatorDisputeCloseLateView,
    OperatorDisputeCloseView,
    OperatorDisputeDetailView,
    OperatorDisputeEvidencePresignGetView,
    OperatorDisputeListView,
    OperatorDisputeRequestMoreEvidenceView,
    OperatorDisputeResolveView,
    OperatorDisputeStartReviewView,
)

urlpatterns = [
    path("", OperatorDisputeListView.as_view(), name="operator_dispute_list"),
    path("<int:pk>/", OperatorDisputeDetailView.as_view(), name="operator_dispute_detail"),
    path(
        "<int:pk>/start-review/",
        OperatorDisputeStartReviewView.as_view(),
        name="operator_dispute_start_review",
    ),
    path(
        "<int:pk>/request-more-evidence/",
        OperatorDisputeRequestMoreEvidenceView.as_view(),
        name="operator_dispute_request_more_evidence",
    ),
    path(
        "<int:pk>/close/",
        OperatorDisputeCloseView.as_view(),
        name="operator_dispute_close",
    ),
    path(
        "<int:pk>/close-as-duplicate/",
        OperatorDisputeCloseDuplicateView.as_view(),
        name="operator_dispute_close_duplicate",
    ),
    path(
        "<int:pk>/close-as-late/",
        OperatorDisputeCloseLateView.as_view(),
        name="operator_dispute_close_late",
    ),
    path(
        "<int:pk>/evidence/<int:evidence_id>/presign-get/",
        OperatorDisputeEvidencePresignGetView.as_view(),
        name="operator_dispute_evidence_presign_get",
    ),
    path(
        "<int:pk>/resolve/",
        OperatorDisputeResolveView.as_view(),
        name="operator_dispute_resolve",
    ),
]
