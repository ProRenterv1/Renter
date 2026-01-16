from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0012_owner_fee_tax_invoice"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="kind",
            field=models.CharField(
                max_length=64,
                choices=[
                    ("BOOKING_CHARGE", "Booking charge"),
                    ("REFUND", "Refund"),
                    ("OWNER_EARNING", "Owner earning"),
                    ("OWNER_PAYOUT", "Owner payout"),
                    ("PLATFORM_FEE", "Platform fee"),
                    ("GST_COLLECTED", "GST collected"),
                    ("DAMAGE_DEPOSIT_HOLD", "Damage deposit hold"),
                    ("DAMAGE_DEPOSIT_CAPTURE", "Damage deposit capture"),
                    ("DAMAGE_DEPOSIT_RELEASE", "Damage deposit release"),
                    ("PROMOTION_CHARGE", "Promotion charge"),
                ],
            ),
        ),
    ]
