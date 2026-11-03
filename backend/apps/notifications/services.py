from django.db import transaction
from django.db.models import Q

from apps.hierarchy.models import Responsibility
from apps.hierarchy.services import accessible_mpps, covers_running
from apps.organizations.models import Membership
from apps.rbac.models import Role
from apps.rbac.services import permissions_for

from .models import Notification
from .tasks import deliver_email, deliver_push


def assigned_to(mpp, responsibility) -> list[Membership]:
    return list(
        Membership.objects.filter(
            is_active=True,
            mpp_assignments__mpp=mpp,
            mpp_assignments__responsibility=responsibility,
            mpp_assignments__ended_at__isnull=True,
        )
    )


def area_managers_of(mpp) -> list[Membership]:
    """Everyone holding the MPP's MCC or covering for one who does, and anyone given this MPP."""
    covering = covers_running().filter(
        absent__mcc_assignments__mcc_id=mpp.mcc_id, absent__mcc_assignments__ended_at__isnull=True
    )
    return list(
        Membership.objects.filter(
            Q(
                mcc_assignments__mcc_id=mpp.mcc_id,
                mcc_assignments__ended_at__isnull=True,
                role_links__role__permissions__contains=["applications.approve_am"],
            )
            | Q(
                pk__in=covering.values("colleague"),
                role_links__role__permissions__contains=["applications.approve_am"],
            )
            | Q(
                mpp_assignments__mpp=mpp,
                mpp_assignments__responsibility=Responsibility.AREA_MANAGER,
                mpp_assignments__ended_at__isnull=True,
            ),
            is_active=True,
        ).distinct()
    )


def holders_of(permission: str) -> list[Membership]:
    roles = Role.objects.filter(permissions__contains=[permission])
    return list(Membership.objects.filter(is_active=True, role_links__role__in=roles).distinct())


def notify(recipients, *, title: str, body: str, application=None) -> None:
    for recipient in recipients:
        notification = Notification.objects.create(
            organization_id=recipient.organization_id,
            recipient=recipient,
            title=title,
            body=body,
            application=application,
        )
        transaction.on_commit(
            lambda pk=notification.pk, org=recipient.organization_id: deliver_email.delay(
                str(pk), str(org)
            )
        )


def _label(application) -> str:
    name = application.data.get("applicant", {}).get("full_name", "")
    return f"{application.form_number} {name}".strip()


def application_awaits_area_manager(application) -> None:
    notify(
        area_managers_of(application.mpp),
        title=f"Application waiting: {_label(application)}",
        body=f"MPP {application.mpp.code} has an application for your approval.",
        application=application,
    )


def _reaches(membership, mpp) -> bool:
    permissions = permissions_for(membership)
    return accessible_mpps(membership, permissions).filter(pk=mpp.pk).exists()


def application_awaits(application, permission: str) -> None:
    """Only the people of that stage who work this form's MCC."""
    notify(
        [holder for holder in holders_of(permission) if _reaches(holder, application.mpp)],
        title=f"Application waiting: {_label(application)}",
        body=f"MPP {application.mpp.code} has an application for your approval.",
        application=application,
    )


def push(recipients, *, title: str, body: str, data: dict[str, str]) -> None:
    """To the phones of these people, once the change that caused it is saved."""
    if not recipients:
        return
    organization = str(recipients[0].organization_id)
    people = [str(recipient.pk) for recipient in recipients]
    transaction.on_commit(lambda: deliver_push.delay(organization, people, title, body, data))


def application_rejected(application, reason: str) -> None:
    facilitators = assigned_to(application.mpp, Responsibility.FACILITATOR)
    notify(
        facilitators,
        title=f"Application returned: {_label(application)}",
        body=f"Please correct and resubmit. Reason: {reason}",
        application=application,
    )
    # The facilitator is in the field: the phone is where they will see it.
    name = application.data.get("applicant", {}).get("full_name", "")
    push(
        facilitators,
        title=f"Form sent back: {name or application.form_number}",
        body=f"{application.form_number} · {reason}"[:180],
        data={
            "source": "member_onboarding",
            "type": "application_rejected",
            "application_id": str(application.pk),
        },
    )


def application_approved(application, tr_code: str) -> None:
    notify(
        assigned_to(application.mpp, Responsibility.FACILITATOR),
        title=f"Member approved: {_label(application)}",
        body=f"Member code: {tr_code}",
        application=application,
    )
