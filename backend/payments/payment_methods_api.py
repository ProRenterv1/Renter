from __future__ import annotations

import logging

import stripe
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PaymentMethod, PaymentSetupIntent
from .stripe_api import (
    StripeConfigurationError,
    StripePaymentError,
    StripeTransientError,
    _ensure_payment_method_for_customer,
    _get_stripe_api_key,
    call_stripe_callable,
    create_or_reuse_setup_intent,
    ensure_stripe_customer,
    fetch_payment_method_details,
)

logger = logging.getLogger(__name__)


class PaymentMethodSerializer(serializers.ModelSerializer):
    stripe_payment_method_id = serializers.CharField()
    stripe_setup_intent_id = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    setup_intent_status = serializers.CharField(write_only=True, required=False, allow_blank=True)
    card_brand = serializers.CharField(write_only=True, required=False, allow_blank=True)
    card_last4 = serializers.CharField(write_only=True, required=False, allow_blank=True)
    card_exp_month = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    card_exp_year = serializers.IntegerField(write_only=True, required=False, allow_null=True)

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
            "stripe_setup_intent_id",
            "setup_intent_status",
            "card_brand",
            "card_last4",
            "card_exp_month",
            "card_exp_year",
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
        setup_intent_id = (validated_data.pop("stripe_setup_intent_id", "") or "").strip()
        setup_intent_status = (validated_data.pop("setup_intent_status", "") or "").strip()
        card_brand = (validated_data.pop("card_brand", "") or "").strip()
        card_last4 = (validated_data.pop("card_last4", "") or "").strip()
        card_exp_month = validated_data.pop("card_exp_month", None)
        card_exp_year = validated_data.pop("card_exp_year", None)

        setup_intent = None
        attached_via_setup_intent = False
        if setup_intent_id:
            setup_intent = PaymentSetupIntent.objects.filter(
                stripe_setup_intent_id=setup_intent_id,
            ).first()
            if setup_intent is None or setup_intent.user_id != user.id:
                raise serializers.ValidationError(
                    {"stripe_setup_intent_id": "Invalid setup_intent_id for this user."}
                )
            attached_via_setup_intent = True
            updates: list[str] = []
            now = timezone.now()
            if setup_intent_status and setup_intent_status != setup_intent.status:
                setup_intent.status = setup_intent_status
                updates.append("status")
            if setup_intent.consumed_at is None:
                setup_intent.consumed_at = now
                updates.append("consumed_at")
            if updates:
                setup_intent.save(update_fields=updates)

        customer_id = call_stripe_callable(
            ensure_stripe_customer,
            primary_kwargs={"user": user, "cache_scope": request},
            fallback_kwargs={"user": user},
        )
        call_stripe_callable(
            _ensure_payment_method_for_customer,
            primary_kwargs={
                "payment_method_id": payment_method_id,
                "customer_id": customer_id,
                "attached_via_setup_intent": attached_via_setup_intent,
                "cache_scope": request,
            },
            fallback_kwargs={
                "payment_method_id": payment_method_id,
                "customer_id": customer_id,
            },
            error_keywords=("cache_scope", "attached_via_setup_intent"),
        )

        details = {}
        if card_brand and card_last4:
            details = {
                "brand": card_brand.upper(),
                "last4": card_last4,
                "exp_month": card_exp_month,
                "exp_year": card_exp_year,
            }
        else:
            details = call_stripe_callable(
                fetch_payment_method_details,
                primary_kwargs={
                    "payment_method_id": payment_method_id,
                    "cache_scope": request,
                },
                fallback_kwargs={"payment_method_id": payment_method_id},
            )

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

    @action(detail=False, methods=["post"], url_path="setup-intent")
    def setup_intent(self, request):
        data = request.data or {}
        intent_type = (
            str(
                (data.get("intent_type") if hasattr(data, "get") else "")
                or PaymentSetupIntent.IntentType.DEFAULT_CARD
            ).strip()
            or PaymentSetupIntent.IntentType.DEFAULT_CARD
        )
        valid_types = {choice for choice, _ in PaymentSetupIntent.IntentType.choices}
        if intent_type not in valid_types:
            return Response(
                {"detail": "intent_type is invalid."},
                status=400,
            )

        try:
            setup_intent = create_or_reuse_setup_intent(
                user=request.user,
                intent_type=intent_type,
                cache_scope=request,
            )
        except StripeTransientError:
            return Response(
                {"detail": "Temporary Stripe issue creating a card setup session."},
                status=503,
            )
        except StripeConfigurationError:
            return Response(
                {"detail": "Stripe is not configured; please try again later."},
                status=503,
            )
        except StripePaymentError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "setup_intent_id": setup_intent.stripe_setup_intent_id,
                "client_secret": setup_intent.client_secret,
                "status": setup_intent.status,
                "intent_type": setup_intent.intent_type,
            }
        )

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
