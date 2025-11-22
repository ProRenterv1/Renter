import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0004_add_promotion_breakdown_fields"),
        ("payments", "0003_ownerpayoutaccount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="booking",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transactions",
                to="bookings.booking",
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="promotion_slot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transactions",
                to="promotions.promotedslot",
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="kind",
            field=models.CharField(
                choices=[
                    ("BOOKING_CHARGE", "Booking charge"),
                    ("REFUND", "Refund"),
                    ("OWNER_EARNING", "Owner earning"),
                    ("PLATFORM_FEE", "Platform fee"),
                    ("DAMAGE_DEPOSIT_CAPTURE", "Damage deposit capture"),
                    ("DAMAGE_DEPOSIT_RELEASE", "Damage deposit release"),
                    ("PROMOTION_CHARGE", "Promotion charge"),
                ],
                max_length=64,
            ),
        ),
    ]
