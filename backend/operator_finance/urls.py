from django.urls import path

from operator_finance.api import (
    OperatorBookingDepositCaptureView,
    OperatorBookingDepositReleaseView,
    OperatorBookingFinanceView,
    OperatorBookingRefundView,
    OperatorOwnerLedgerExportView,
    OperatorPlatformRevenueExportView,
    OperatorTransactionListView,
)

app_name = "operator_finance"

urlpatterns = [
    path(
        "transactions/", OperatorTransactionListView.as_view(), name="operator_finance_transactions"
    ),
    path(
        "bookings/<int:pk>/finance",
        OperatorBookingFinanceView.as_view(),
        name="operator_finance_booking",
    ),
    path(
        "bookings/<int:pk>/refund",
        OperatorBookingRefundView.as_view(),
        name="operator_finance_booking_refund",
    ),
    path(
        "bookings/<int:pk>/deposit/capture",
        OperatorBookingDepositCaptureView.as_view(),
        name="operator_finance_deposit_capture",
    ),
    path(
        "bookings/<int:pk>/deposit/release",
        OperatorBookingDepositReleaseView.as_view(),
        name="operator_finance_deposit_release",
    ),
    path(
        "exports/platform-revenue.csv",
        OperatorPlatformRevenueExportView.as_view(),
        name="operator_finance_platform_revenue_export",
    ),
    path(
        "exports/owner-ledger.csv",
        OperatorOwnerLedgerExportView.as_view(),
        name="operator_finance_owner_ledger_export",
    ),
]
