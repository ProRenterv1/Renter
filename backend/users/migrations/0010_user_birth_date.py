from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0009_user_rating_user_review_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="birth_date",
            field=models.DateField(blank=True, help_text="Optional birth date for KYC.", null=True),
        ),
    ]
