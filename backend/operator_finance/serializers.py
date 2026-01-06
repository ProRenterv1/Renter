from decimal import Decimal

from rest_framework import serializers

from bookings.models import Booking
from payments.models import Transaction


def _format_money(value) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


class OperatorTransactionUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.SerializerMethodField()

    def get_name(self, obj):
        full_name = (obj.get_full_name() or "").strip()
        if full_name:
            return full_name
        return obj.username or obj.email or ""


class OperatorTransactionSerializer(serializers.ModelSerializer):
    user = OperatorTransactionUserSerializer(read_only=True)
    amount = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id",
            "created_at",
            "kind",
            "amount",
            "currency",
            "stripe_id",
            "booking_id",
            "user",
        ]
        read_only_fields = fields

    def get_amount(self, obj: Transaction) -> str:
        return _format_money(obj.amount)

    def get_currency(self, obj: Transaction) -> str:
        code = (obj.currency or "").upper()
        return code or "CAD"


class BookingFinanceSerializer(serializers.ModelSerializer):
    booking_id = serializers.IntegerField(source="id", read_only=True)
    stripe = serializers.SerializerMethodField()
    ledger = OperatorTransactionSerializer(source="transactions", many=True, read_only=True)

    class Meta:
        model = Booking
        fields = ["booking_id", "stripe", "ledger"]
        read_only_fields = fields

    def get_stripe(self, obj: Booking) -> dict:
        return {
            "charge_payment_intent_id": obj.charge_payment_intent_id,
            "deposit_hold_id": obj.deposit_hold_id,
        }
