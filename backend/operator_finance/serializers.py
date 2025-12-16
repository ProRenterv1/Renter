from decimal import Decimal

from rest_framework import serializers

from bookings.models import Booking
from payments.models import Transaction


def _format_money(value) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


class OperatorTransactionSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    booking_status = serializers.CharField(source="booking.status", read_only=True)
    listing_title = serializers.CharField(source="booking.listing.title", read_only=True)
    amount = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id",
            "kind",
            "amount",
            "currency",
            "stripe_id",
            "user_id",
            "user_email",
            "booking_id",
            "booking_status",
            "listing_title",
            "created_at",
        ]
        read_only_fields = fields

    def get_amount(self, obj: Transaction) -> str:
        return _format_money(obj.amount)

    def get_currency(self, obj: Transaction) -> str:
        code = (obj.currency or "").upper()
        return code or "CAD"


class OperatorBookingFinanceSerializer(serializers.ModelSerializer):
    transactions = OperatorTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "status",
            "charge_payment_intent_id",
            "deposit_hold_id",
            "deposit_authorized_at",
            "deposit_released_at",
            "deposit_release_scheduled_at",
            "deposit_locked",
            "totals",
            "transactions",
        ]
        read_only_fields = fields
