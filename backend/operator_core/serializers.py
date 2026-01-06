from __future__ import annotations

from rest_framework import serializers

from operator_core.models import OperatorAuditEvent


class OperatorAuditEventListSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = OperatorAuditEvent
        fields = [
            "id",
            "action",
            "entity_type",
            "entity_id",
            "reason",
            "created_at",
            "actor",
        ]
        read_only_fields = fields

    def get_actor(self, obj: OperatorAuditEvent) -> dict | None:
        actor = getattr(obj, "actor", None)
        if not actor:
            return None
        name = (getattr(actor, "get_full_name", lambda: "")() or "").strip()
        if not name:
            name = getattr(actor, "username", None) or getattr(actor, "email", "")
        return {
            "id": actor.id,
            "name": name,
            "email": getattr(actor, "email", None),
        }


class OperatorAuditEventDetailSerializer(OperatorAuditEventListSerializer):
    class Meta(OperatorAuditEventListSerializer.Meta):
        fields = OperatorAuditEventListSerializer.Meta.fields + [
            "before_json",
            "after_json",
            "meta_json",
            "ip",
            "user_agent",
        ]
        read_only_fields = fields
