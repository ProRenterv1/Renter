from django.urls import path

from operator_listings.api import (
    OperatorListingActivateView,
    OperatorListingDeactivateView,
    OperatorListingDetailView,
    OperatorListingEmergencyEditView,
    OperatorListingListView,
    OperatorListingMarkNeedsReviewView,
)

app_name = "operator_listings"

urlpatterns = [
    path("", OperatorListingListView.as_view(), name="operator_listing_list"),
    path(
        "<int:pk>/deactivate/",
        OperatorListingDeactivateView.as_view(),
        name="operator_listing_deactivate",
    ),
    path(
        "<int:pk>/activate/",
        OperatorListingActivateView.as_view(),
        name="operator_listing_activate",
    ),
    path(
        "<int:pk>/mark-needs-review/",
        OperatorListingMarkNeedsReviewView.as_view(),
        name="operator_listing_mark_needs_review",
    ),
    path(
        "<int:pk>/emergency-edit/",
        OperatorListingEmergencyEditView.as_view(),
        name="operator_listing_emergency_edit",
    ),
    path("<int:pk>/", OperatorListingDetailView.as_view(), name="operator_listing_detail"),
]
