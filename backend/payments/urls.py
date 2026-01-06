from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .payment_methods_api import PaymentMethodViewSet
from .stripe_api import stripe_webhook

app_name = "payments"

router = DefaultRouter()
router.register("methods", PaymentMethodViewSet, basename="payment-method")

urlpatterns = [
    path("stripe/webhook/", stripe_webhook, name="stripe_webhook"),
    path("", include(router.urls)),
]
