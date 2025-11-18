from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="charge_payment_intent_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Stripe PaymentIntent ID for the rental charge (base + renter fee).",
                max_length=120,
            ),
        ),
    ]
