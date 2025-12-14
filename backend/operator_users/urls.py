from django.urls import path

from operator_users.api import (
    OperatorUserDetailView,
    OperatorUserListView,
    OperatorUserMarkSuspiciousView,
    OperatorUserReinstateView,
    OperatorUserResendVerificationView,
    OperatorUserSendPasswordResetView,
    OperatorUserSetRestrictionsView,
    OperatorUserSuspendView,
)

urlpatterns = [
    path("", OperatorUserListView.as_view(), name="operator_user_list"),
    path("<int:pk>/", OperatorUserDetailView.as_view(), name="operator_user_detail"),
    path("<int:pk>/suspend/", OperatorUserSuspendView.as_view(), name="operator_user_suspend"),
    path(
        "<int:pk>/reinstate/",
        OperatorUserReinstateView.as_view(),
        name="operator_user_reinstate",
    ),
    path(
        "<int:pk>/set-restrictions/",
        OperatorUserSetRestrictionsView.as_view(),
        name="operator_user_set_restrictions",
    ),
    path(
        "<int:pk>/mark-suspicious/",
        OperatorUserMarkSuspiciousView.as_view(),
        name="operator_user_mark_suspicious",
    ),
    path(
        "<int:pk>/send-password-reset/",
        OperatorUserSendPasswordResetView.as_view(),
        name="operator_user_send_password_reset",
    ),
    path(
        "<int:pk>/resend-verification/",
        OperatorUserResendVerificationView.as_view(),
        name="operator_user_resend_verification",
    ),
]
