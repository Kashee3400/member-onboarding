from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record_event

from .models import Mcc, MccAssignment, Mpp, MppAssignment, Responsibility

# A person can only hold an MPP if their role lets them do that job.
REQUIRED_PERMISSION = {
    Responsibility.FACILITATOR: "applications.create",
    Responsibility.AREA_MANAGER: "applications.approve_am",
}


def accessible_mpps(membership, permissions):
    """Every query for MPP-owned data must start here, so a transfer moves access at once."""
    direct = Q(assignments__membership=membership, assignments__ended_at__isnull=True)
    allotted = Q(mcc__assignments__membership=membership, mcc__assignments__ended_at__isnull=True)
    # Someone given MCCs works those, even in a role that could see everything. A head,
    # given none, keeps the whole organization.
    has_mccs = MccAssignment.objects.filter(membership=membership, ended_at__isnull=True).exists()
    if "mpp.view_all" in permissions and not has_mccs:
        return Mpp.objects.all()
    return Mpp.objects.filter(direct | allotted).distinct()


def _end(assignment, actor):
    assignment.ended_at = timezone.now()
    assignment.ended_by = actor
    assignment.save(update_fields=["ended_at", "ended_by", "updated_at"])


@transaction.atomic
def assign_mpp(*, mpp, membership, responsibility, actor):
    """Assign an MPP, transferring it if someone else holds that responsibility."""
    Mpp.objects.select_for_update().get(pk=mpp.pk)
    current = MppAssignment.objects.filter(
        mpp=mpp, responsibility=responsibility, ended_at__isnull=True
    ).first()

    if current and current.membership_id == membership.id:
        return current
    if current:
        _end(current, actor)

    assignment = MppAssignment.objects.create(
        mpp=mpp, membership=membership, responsibility=responsibility, assigned_by=actor
    )
    record_event(
        "mpp.assigned",
        actor=actor,
        target=mpp,
        metadata={
            "responsibility": responsibility,
            "from_membership": str(current.membership_id) if current else None,
            "to_membership": str(membership.id),
        },
    )
    return assignment


@transaction.atomic
def assign_mcc(*, mcc, membership, actor):
    """Allot an MCC to someone who approves forms. Anyone already there stays."""
    Mcc.objects.select_for_update().get(pk=mcc.pk)
    current = MccAssignment.objects.filter(
        mcc=mcc, membership=membership, ended_at__isnull=True
    ).first()
    if current:
        return current

    assignment = MccAssignment.objects.create(mcc=mcc, membership=membership, assigned_by=actor)
    record_event(
        "mcc.assigned", actor=actor, target=mcc, metadata={"membership": str(membership.id)}
    )
    return assignment


@transaction.atomic
def end_mcc_assignment(*, mcc, membership, actor) -> bool:
    Mcc.objects.select_for_update().get(pk=mcc.pk)
    current = MccAssignment.objects.filter(
        mcc=mcc, membership=membership, ended_at__isnull=True
    ).first()
    if current is None:
        return False

    _end(current, actor)
    record_event(
        "mcc.unassigned",
        actor=actor,
        target=mcc,
        metadata={"membership": str(current.membership_id)},
    )
    return True


@transaction.atomic
def end_assignment(*, mpp, responsibility, actor) -> bool:
    Mpp.objects.select_for_update().get(pk=mpp.pk)
    current = MppAssignment.objects.filter(
        mpp=mpp, responsibility=responsibility, ended_at__isnull=True
    ).first()
    if current is None:
        return False

    _end(current, actor)
    record_event(
        "mpp.unassigned",
        actor=actor,
        target=mpp,
        metadata={"responsibility": responsibility, "membership": str(current.membership_id)},
    )
    return True


def end_assignments_for(membership, *, actor) -> None:
    """Free a departing person's MPPs and MCCs, so they show as needing a new owner."""
    held = MccAssignment.objects.filter(membership=membership, ended_at__isnull=True)
    for assignment in held.select_related("mcc"):
        end_mcc_assignment(mcc=assignment.mcc, membership=membership, actor=actor)
    active = MppAssignment.objects.filter(membership=membership, ended_at__isnull=True)
    for assignment in active.select_related("mpp"):
        end_assignment(mpp=assignment.mpp, responsibility=assignment.responsibility, actor=actor)
