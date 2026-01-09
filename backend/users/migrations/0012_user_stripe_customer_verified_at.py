from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0011_socialidentity"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="stripe_customer_verified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Last time we confirmed the stored Stripe customer still exists.",
                null=True,
            ),
        ),
    ]

