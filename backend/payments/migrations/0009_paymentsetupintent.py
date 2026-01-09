import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0008_add_owner_payout_kind"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentSetupIntent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("intent_type", models.CharField(choices=[("default_card", "Default card"), ("promotion_card", "Promotion card")], default="default_card", max_length=64)),
                ("stripe_setup_intent_id", models.CharField(max_length=255, unique=True)),
                ("client_secret", models.TextField()),
                ("status", models.CharField(default="requires_confirmation", max_length=64)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payment_setup_intents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="paymentsetupintent",
            index=models.Index(fields=["user", "intent_type"], name="payments_pa_user_id_7b8a32_idx"),
        ),
        migrations.AddIndex(
            model_name="paymentsetupintent",
            index=models.Index(fields=["user", "consumed_at"], name="payments_pa_user_id_497c5e_idx"),
        ),
    ]
