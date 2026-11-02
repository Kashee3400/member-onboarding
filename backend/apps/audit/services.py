from apps.core.context import get_request_context
from apps.core.tenancy import get_current_organization_id

from .models import AuditEvent


def record_event(action: str, *, actor=None, target=None, metadata: dict | None = None):
    context = get_request_context()
    return AuditEvent.objects.create(
        organization_id=get_current_organization_id(),
        actor_id=actor.pk if actor else None,
        action=action,
        target_type=target._meta.label_lower if target else "",
        target_id=str(target.pk) if target else "",
        request_id=context.request_id,
        ip_address=context.ip_address,
        metadata=metadata or {},
    )
