from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0009_booking_deposit_locked_booking_is_disputed"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="deposit_attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="booking",
            name="deposit_authorized_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When a damage deposit authorization succeeded.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="renter_stripe_customer_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Cached Stripe customer id used for charges/deposit holds.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="renter_stripe_payment_method_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Payment method id to reuse for deposit authorization.",
                max_length=120,
            ),
        ),
    ]
