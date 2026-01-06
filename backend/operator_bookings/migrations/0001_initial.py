import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("bookings", "0010_booking_deposit_authorization_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("type", models.CharField(choices=[("status_change", "Status change"), ("email_sent", "Email sent"), ("email_failed", "Email failed"), ("operator_action", "Operator action"), ("dispute_opened", "Dispute opened")], max_length=32)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="operator_booking_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="bookings.booking",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="bookingevent",
            index=models.Index(fields=["booking", "created_at"], name="operator_bo_booking_e7cbaf_idx"),
        ),
        migrations.AddIndex(
            model_name="bookingevent",
            index=models.Index(fields=["type", "created_at"], name="operator_bo_type_crea_7fa74e_idx"),
        ),
    ]
