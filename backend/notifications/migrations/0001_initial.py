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
            name="NotificationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("channel", models.CharField(choices=[("email", "Email"), ("sms", "SMS")], max_length=8)),
                ("type", models.CharField(max_length=128)),
                ("booking_id", models.IntegerField(blank=True, null=True)),
                ("status", models.CharField(choices=[("sent", "Sent"), ("failed", "Failed")], max_length=8)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notification_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["created_at"], name="notification_created_65a70b_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["booking_id", "created_at"], name="notification_booking_7d8d32_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(fields=["type", "created_at"], name="notification_type_cre_136b3c_idx"),
        ),
    ]
