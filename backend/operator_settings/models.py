from django.conf import settings
from django.db import models


class DbSetting(models.Model):
    class ValueType(models.TextChoices):
        BOOL = "bool", "bool"
        INT = "int", "int"
        DECIMAL = "decimal", "decimal"
        STR = "str", "str"
        JSON = "json", "json"

    key = models.CharField(max_length=128, db_index=True)
    value_json = models.JSONField()
    value_type = models.CharField(max_length=16, choices=ValueType.choices)
    description = models.TextField(blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operator_db_settings_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)
    effective_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["key", "effective_at", "updated_at"], name="opset_db_key_eff_upd_idx"
            ),
            models.Index(fields=["updated_at"], name="opset_db_updated_at_idx"),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.key} ({self.value_type})"

    def _has_versioning_changes(self, existing: "DbSetting") -> bool:
        return (
            existing.key != self.key
            or existing.value_json != self.value_json
            or existing.value_type != self.value_type
            or existing.description != self.description
            or existing.updated_by_id != self.updated_by_id
            or existing.effective_at != self.effective_at
        )

    def save(self, *args, **kwargs):
        if self.pk is not None:
            using = kwargs.get("using") or self._state.db
            existing = type(self).objects.using(using).filter(pk=self.pk).first()
            if existing is not None:
                if not self._has_versioning_changes(existing):
                    return
                self.pk = None
                self._state.adding = True
                kwargs.pop("force_update", None)
                kwargs.pop("update_fields", None)
                kwargs["force_insert"] = True
        super().save(*args, **kwargs)


class FeatureFlag(models.Model):
    key = models.CharField(max_length=128, unique=True)
    enabled = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operator_feature_flags_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class MaintenanceBanner(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "info"
        WARNING = "warning", "warning"
        ERROR = "error", "error"

    enabled = models.BooleanField(default=False)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.INFO)
    message = models.TextField(blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operator_maintenance_banners_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.severity}: {'on' if self.enabled else 'off'}"


class OperatorJobRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "queued"
        RUNNING = "running", "running"
        SUCCEEDED = "succeeded", "succeeded"
        FAILED = "failed", "failed"

    name = models.CharField(max_length=128, db_index=True)
    params = models.JSONField(default=dict, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operator_job_runs_requested",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    output_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["name", "status", "created_at"], name="opset_job_n_status_created_idx"
            ),
            models.Index(fields=["status", "created_at"], name="opset_job_status_created_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"
