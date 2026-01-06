import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0010_user_birth_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("google", "Google")], max_length=32)),
                ("provider_user_id", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="socialidentity",
            constraint=models.UniqueConstraint(
                fields=("provider", "provider_user_id"),
                name="uniq_social_provider_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="socialidentity",
            constraint=models.UniqueConstraint(
                fields=("user", "provider"),
                name="uniq_social_user_provider",
            ),
        ),
    ]
