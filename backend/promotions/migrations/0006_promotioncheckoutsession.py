import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0005_promotedslot_promo_active_window_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="PromotionCheckoutSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("amount_cents", models.PositiveIntegerField()),
                ("stripe_session_id", models.CharField(max_length=255, unique=True)),
                ("session_url", models.TextField()),
                ("status", models.CharField(default="open", max_length=32)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "listing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promotion_checkout_sessions",
                        to="listings.listing",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promotion_checkout_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="promotioncheckoutsession",
            index=models.Index(
                fields=("listing", "owner"),
                name="promo_checkout_listing_owner_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="promotioncheckoutsession",
            index=models.Index(
                fields=("owner", "consumed_at"),
                name="promo_checkout_owner_consumed_idx",
            ),
        ),
    ]
