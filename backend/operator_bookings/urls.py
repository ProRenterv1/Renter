from django.urls import path

from operator_bookings.api import OperatorBookingDetailView, OperatorBookingListView

app_name = "operator_bookings"

urlpatterns = [
    path("", OperatorBookingListView.as_view(), name="operator_booking_list"),
    path("<int:pk>/", OperatorBookingDetailView.as_view(), name="operator_booking_detail"),
]
