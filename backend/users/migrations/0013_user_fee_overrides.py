import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_user_stripe_customer_verified_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="owner_fee_exempt",
            field=models.BooleanField(
                default=False, help_text="When true, waive owner-side platform fees for this user."
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="renter_fee_exempt",
            field=models.BooleanField(
                default=False, help_text="When true, waive renter-side platform fees for this user."
            ),
        ),
        migrations.CreateModel(
            name="UserFeeOverride",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("renter_fee_exempt", models.BooleanField(default=False)),
                ("owner_fee_exempt", models.BooleanField(default=False)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fee_override",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at",),
            },
        ),
    ]
