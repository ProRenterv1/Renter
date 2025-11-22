from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0003_remove_promotedslot_plan_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotedslot",
            name="base_price_cents",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="promotedslot",
            name="gst_cents",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
