"""
The morning note to every approver: how many forms wait for them, and how many are
late. Counted exactly as their home page counts, so the two never disagree.
"""

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.applications.home import _my_queue
from apps.applications.services import OVERDUE_DAYS, visible_applications
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership, Organization
from apps.rbac.catalog import APPROVAL_PERMISSIONS
from apps.rbac.services import permissions_for

from .models import MorningSummary
from .services import notify

logger = structlog.get_logger(__name__)


def _wording(waiting: int, overdue: int) -> str:
    text = f"{waiting} form waits for you" if waiting == 1 else f"{waiting} forms wait for you"
    if overdue:
        late = "" if waiting == 1 else f" {overdue} of them"
        text += f",{late} over {OVERDUE_DAYS} days"
    return text


def _approvers():
    return (
        Membership.objects.filter(
            is_active=True,
            user__is_active=True,
            role_links__role__permissions__overlap=sorted(APPROVAL_PERMISSIONS),
        )
        .exclude(notification_preference__morning_summary=False)
        .select_related("user")
        .distinct()
    )


def send_for_organization(day) -> int:
    """Run inside the organization's context. Returns how many were sent."""
    sent = 0
    for membership in _approvers():
        permissions = permissions_for(membership)
        queue = _my_queue(membership, visible_applications(membership, permissions))
        if not queue["waiting"]:
            continue
        # A savepoint each, so one clash with a run already sending does not undo the rest.
        with transaction.atomic():
            _, created = MorningSummary.objects.get_or_create(
                recipient=membership,
                day=day,
                defaults={"waiting": queue["waiting"], "overdue": queue["overdue"]},
            )
            if not created:
                continue
            notify(
                [membership],
                title=_wording(queue["waiting"], queue["overdue"]),
                body=f"Open your queue to work through them: {settings.PORTAL_URL}/approvals",
            )
        sent += 1
    return sent


def send_morning_summaries(day=None) -> int:
    """Every organization, each in its own context so row level security lets it read."""
    day = day or timezone.localdate()
    total = 0
    for organization_id in Organization.objects.filter(is_active=True).values_list("pk", flat=True):
        with organization_context(organization_id):
            sent = send_for_organization(day)
        logger.info("morning_summary_sent", organization=str(organization_id), sent=sent)
        total += sent
    return total
