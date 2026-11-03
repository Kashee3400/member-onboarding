"""
Each organization at a glance, for the platform operator: how much it is used,
what is stuck, what is failing and what is still to set up.
"""

from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone

from apps.applications.models import Application, Member, ReviewStepAccess, Signatory, Status
from apps.applications.review_settings import overdue_days
from apps.audit.models import AuditEvent
from apps.branding.models import Branding
from apps.configuration.models import IntegrationConfig
from apps.core.tenancy import organization_context
from apps.federation.models import TrustedIssuer
from apps.hierarchy.models import Mpp
from apps.notifications.models import DeliveryFailure
from apps.organizations.models import Membership

from .quotas import storage_bytes

PENDING = (Status.PENDING_AM, Status.PENDING_CS, Status.PENDING_FINANCE)


def _setup(organization) -> dict:
    integrations = {
        row.kind: row.is_enabled for row in IntegrationConfig.objects.only("kind", "is_enabled")
    }
    branding = Branding.objects.first()
    return {
        "branding": bool(branding and branding.logo_path),
        "email_domain": bool(branding and branding.email_domain),
        "mail": integrations.get("mail", False),
        "sms": integrations.get("sms", False),
        "push": integrations.get("push", False),
        "review_steps": ReviewStepAccess.objects.exists(),
        "signatories": Signatory.objects.count(),
        "connected_apps": TrustedIssuer.objects.filter(
            organization=organization, is_active=True
        ).count(),
        "mpps": Mpp.objects.filter(is_active=True).count(),
    }


def organization_health(organization) -> dict:
    now = timezone.now()
    week = now - timedelta(days=7)
    with organization_context(organization.id):
        by_status = dict(
            Application.objects.values_list("status").annotate(count=Count("id")).order_by()
        )
        late = now - timedelta(days=overdue_days())
        failures = dict(
            DeliveryFailure.objects.filter(created_at__gte=week)
            .values_list("channel")
            .annotate(count=Count("id"))
            .order_by()
        )
        health = {
            "forms_total": sum(by_status.values()),
            "forms_this_week": Application.objects.filter(created_at__gte=week).count(),
            "pending": sum(by_status.get(stage, 0) for stage in PENDING),
            "late": Application.objects.filter(status__in=PENDING, updated_at__lt=late).count(),
            "sent_back": by_status.get(Status.REJECTED, 0),
            "members": Member.objects.count(),
            "staff": Membership.objects.filter(is_active=True).count(),
            "last_activity": AuditEvent.objects.aggregate(last=Max("occurred_at"))["last"],
            "failures_this_week": {
                channel: failures.get(channel, 0) for channel in DeliveryFailure.Channel.values
            },
            "storage_bytes": storage_bytes(organization.id),
            "storage_limit_mb": organization.storage_limit_mb,
            "setup": _setup(organization),
        }
    return health
