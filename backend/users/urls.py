from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .api import (
    ContactVerificationRequestView,
    ContactVerificationVerifyView,
    FlexibleTokenObtainPairView,
    GoogleLoginView,
    LoginEventListView,
    MeView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PublicProfileView,
    SignupView,
    TwoFactorLoginResendView,
    TwoFactorLoginVerifyView,
    TwoFactorSettingsView,
)

app_name = "users"

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("token/", FlexibleTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("google/", GoogleLoginView.as_view(), name="google_login"),
    path("me/", MeView.as_view(), name="me"),
    path("public/<int:pk>/", PublicProfileView.as_view(), name="public_profile"),
    path(
        "two-factor/settings/",
        TwoFactorSettingsView.as_view(),
        name="two_factor_settings",
    ),
    path(
        "two-factor/verify-login/",
        TwoFactorLoginVerifyView.as_view(),
        name="two_factor_verify_login",
    ),
    path(
        "two-factor/resend-login/",
        TwoFactorLoginResendView.as_view(),
        name="two_factor_resend_login",
    ),
    path("change-password/", PasswordChangeView.as_view(), name="change_password"),
    path(
        "password-reset/request/", PasswordResetRequestView.as_view(), name="password_reset_request"
    ),
    path("password-reset/verify/", PasswordResetVerifyView.as_view(), name="password_reset_verify"),
    path(
        "password-reset/complete/",
        PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path(
        "contact-verification/request/",
        ContactVerificationRequestView.as_view(),
        name="contact_verification_request",
    ),
    path(
        "contact-verification/verify/",
        ContactVerificationVerifyView.as_view(),
        name="contact_verification_verify",
    ),
    path(
        "login-events/",
        LoginEventListView.as_view(),
        name="login_events",
    ),
]
