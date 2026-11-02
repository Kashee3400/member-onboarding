from django.db import models

from apps.core.models import UUIDModel


class AuditEvent(UUIDModel):
    """
    Append-only record of who did what. A database trigger rejects UPDATE and
    DELETE. IDs are plain values, not foreign keys, so an event outlives what it
    refers to. Never put secrets or personal identifiers in `metadata`.
    """

    occurred_at = models.DateTimeField(auto_now_add=True)
    organization_id = models.UUIDField(null=True, blank=True)
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_event"
        indexes = [
            models.Index(fields=["organization_id", "-occurred_at"], name="audit_org_time_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
        ]

    def __str__(self):
        return f"{self.action} @ {self.occurred_at}"
