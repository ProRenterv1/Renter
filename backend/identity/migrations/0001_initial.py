"""Initial migration for the identity app."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IdentityVerification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("verified", "Verified"),
                            ("failed", "Failed"),
                            ("canceled", "Canceled"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("session_id", models.CharField(max_length=255, unique=True)),
                ("last_error_code", models.CharField(blank=True, default="", max_length=64)),
                (
                    "last_error_reason",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="identity_verifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="identityverification",
            index=models.Index(
                fields=["user", "status"],
                name="identity_id_user_id_fb1f3d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="identityverification",
            index=models.Index(
                fields=["session_id"],
                name="identity_id_session_a102f5_idx",
            ),
        ),
    ]
