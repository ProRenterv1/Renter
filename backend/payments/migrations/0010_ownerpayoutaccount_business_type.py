from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0009_paymentsetupintent"),
    ]

    operations = [
        migrations.AddField(
            model_name="ownerpayoutaccount",
            name="business_type",
            field=models.CharField(
                default="individual",
                help_text="Stripe business_type (individual/company) chosen by the owner.",
                max_length=32,
            ),
        ),
    ]
