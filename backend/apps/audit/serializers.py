from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "occurred_at",
            "actor_id",
            "actor_name",
            "action",
            "target_type",
            "target_id",
            "request_id",
            "ip_address",
            "metadata",
        ]

    def get_actor_name(self, event) -> str:
        return self.context.get("actor_names", {}).get(event.actor_id, "")
