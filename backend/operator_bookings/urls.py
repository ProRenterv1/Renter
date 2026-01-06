from django.urls import path

from operator_bookings.api import (
    OperatorBookingAdjustDatesView,
    OperatorBookingDetailView,
    OperatorBookingForceCancelView,
    OperatorBookingForceCompleteView,
    OperatorBookingListView,
    OperatorBookingResendNotificationsView,
)

app_name = "operator_bookings"

urlpatterns = [
    path("", OperatorBookingListView.as_view(), name="operator_booking_list"),
    path("<int:pk>/", OperatorBookingDetailView.as_view(), name="operator_booking_detail"),
    path(
        "<int:pk>/force-cancel/",
        OperatorBookingForceCancelView.as_view(),
        name="operator_booking_force_cancel",
    ),
    path(
        "<int:pk>/force-complete/",
        OperatorBookingForceCompleteView.as_view(),
        name="operator_booking_force_complete",
    ),
    path(
        "<int:pk>/adjust-dates/",
        OperatorBookingAdjustDatesView.as_view(),
        name="operator_booking_adjust_dates",
    ),
    path(
        "<int:pk>/resend-notifications/",
        OperatorBookingResendNotificationsView.as_view(),
        name="operator_booking_resend_notifications",
    ),
]
