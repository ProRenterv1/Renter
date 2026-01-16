from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0013_add_damage_deposit_hold_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="stripe_available_on",
            field=models.DateTimeField(
                blank=True,
                help_text="Stripe balance transaction available_on timestamp (UTC).",
                null=True,
            ),
        ),
    ]
