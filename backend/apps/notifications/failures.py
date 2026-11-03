import structlog

from apps.core.tenancy import get_current_organization_id

logger = structlog.get_logger(__name__)


def record_failure(channel: str, reason: str) -> None:
    """Notes a delivery that failed. Never raises: the failure itself is already handled."""
    if get_current_organization_id() is None:
        return
    from .models import DeliveryFailure

    try:
        DeliveryFailure.objects.create(channel=channel, reason=reason[:200])
    except Exception:  # noqa: BLE001
        logger.warning("delivery_failure_not_recorded", channel=channel)
