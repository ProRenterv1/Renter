from __future__ import annotations

from rest_framework import serializers

from operator_settings.models import DbSetting, FeatureFlag, MaintenanceBanner, OperatorJobRun


class DbSettingSerializer(serializers.ModelSerializer):
    updated_by_id = serializers.IntegerField(read_only=True)
    updated_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DbSetting
        fields = [
            "id",
            "key",
            "value_type",
            "value_json",
            "description",
            "effective_at",
            "updated_at",
            "updated_by_id",
            "updated_by_name",
        ]

    def get_updated_by_name(self, obj: DbSetting) -> str | None:
        user = getattr(obj, "updated_by", None)
        if not user:
            return None
        full_name = (user.get_full_name() or "").strip()
        if full_name:
            return full_name
        if getattr(user, "username", ""):
            return user.username
        return f"user-{user.pk}"


class DbSettingPutSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=128)
    value_type = serializers.ChoiceField(choices=DbSetting.ValueType.choices)
    value = serializers.JSONField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    effective_at = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_key(self, value: str) -> str:
        key = (value or "").strip()
        if not key:
            raise serializers.ValidationError("key is required")
        return key

    def validate_reason(self, value: str) -> str:
        reason = (value or "").strip()
        if not reason:
            raise serializers.ValidationError("reason is required")
        return reason

    def validate(self, attrs: dict) -> dict:
        value_type = attrs.get("value_type")
        value = attrs.get("value")

        if value_type == DbSetting.ValueType.BOOL and type(value) is not bool:
            raise serializers.ValidationError({"value": "value must be a boolean"})
        if value_type == DbSetting.ValueType.INT and type(value) is not int:
            raise serializers.ValidationError({"value": "value must be an integer"})
        if value_type == DbSetting.ValueType.DECIMAL and not isinstance(value, str):
            raise serializers.ValidationError({"value": "value must be a decimal string"})
        if value_type == DbSetting.ValueType.STR and not isinstance(value, str):
            raise serializers.ValidationError({"value": "value must be a string"})

        return attrs


class FeatureFlagSerializer(serializers.ModelSerializer):
    updated_by_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = FeatureFlag
        fields = ["id", "key", "enabled", "updated_at", "updated_by_id"]


class FeatureFlagPutSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=128)
    enabled = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_key(self, value: str) -> str:
        key = (value or "").strip()
        if not key:
            raise serializers.ValidationError("key is required")
        return key

    def validate_reason(self, value: str) -> str:
        reason = (value or "").strip()
        if not reason:
            raise serializers.ValidationError("reason is required")
        return reason


class MaintenanceBannerSerializer(serializers.ModelSerializer):
    updated_by_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = MaintenanceBanner
        fields = ["id", "enabled", "severity", "message", "updated_at", "updated_by_id"]


class MaintenanceBannerPutSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    severity = serializers.ChoiceField(choices=MaintenanceBanner.Severity.choices)
    message = serializers.CharField(required=False, allow_blank=True, default="")
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_reason(self, value: str) -> str:
        reason = (value or "").strip()
        if not reason:
            raise serializers.ValidationError("reason is required")
        return reason


class OperatorJobRunSerializer(serializers.ModelSerializer):
    requested_by_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = OperatorJobRun
        fields = [
            "id",
            "name",
            "params",
            "status",
            "output_json",
            "requested_by_id",
            "created_at",
            "finished_at",
        ]


class OperatorRunJobSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    params = serializers.JSONField(required=False, default=dict)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("name is required")
        return name

    def validate_reason(self, value: str) -> str:
        reason = (value or "").strip()
        if not reason:
            raise serializers.ValidationError("reason is required")
        return reason

    def validate_params(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("params must be an object")
        return value
