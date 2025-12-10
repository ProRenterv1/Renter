from __future__ import annotations

import logging

import stripe
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PaymentMethod
from .stripe_api import (
    _ensure_payment_method_for_customer,
    _get_stripe_api_key,
    ensure_stripe_customer,
    fetch_payment_method_details,
)

logger = logging.getLogger(__name__)


class PaymentMethodSerializer(serializers.ModelSerializer):
    stripe_payment_method_id = serializers.CharField(write_only=True)

    class Meta:
        model = PaymentMethod
        fields = [
            "id",
            "brand",
            "last4",
            "exp_month",
            "exp_year",
            "is_default",
            "stripe_payment_method_id",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "brand",
            "last4",
            "exp_month",
            "exp_year",
            "is_default",
            "created_at",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        payment_method_id = validated_data["stripe_payment_method_id"]
        customer_id = ensure_stripe_customer(user)
        _ensure_payment_method_for_customer(payment_method_id, customer_id)
        details = fetch_payment_method_details(payment_method_id)

        brand = str(details.get("brand", "") or "").upper()
        last4 = str(details.get("last4", "") or "")
        is_default = not PaymentMethod.objects.filter(user=user).exists()

        return PaymentMethod.objects.create(
            user=user,
            stripe_payment_method_id=payment_method_id,
            brand=brand,
            last4=last4,
            exp_month=details.get("exp_month"),
            exp_year=details.get("exp_year"),
            is_default=is_default,
        )


class PaymentMethodViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentMethodSerializer

    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)

    def perform_destroy(self, instance: PaymentMethod) -> None:
        payment_method_id = instance.stripe_payment_method_id
        if payment_method_id:
            try:
                stripe.api_key = _get_stripe_api_key()
                stripe.PaymentMethod.detach(payment_method_id)
            except stripe.error.StripeError as exc:
                logger.warning(
                    "payments: failed to detach payment method %s from Stripe: %s",
                    payment_method_id,
                    exc,
                )
        instance.delete()

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        pm = self.get_object()
        PaymentMethod.objects.filter(user=request.user, is_default=True).exclude(pk=pm.pk).update(
            is_default=False
        )
        if not pm.is_default:
            pm.is_default = True
            pm.save(update_fields=["is_default", "updated_at"])
        serializer = self.get_serializer(pm)
        return Response(serializer.data)
