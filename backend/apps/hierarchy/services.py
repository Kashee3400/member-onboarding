from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record_event
from apps.rbac.catalog import APPROVAL_PERMISSIONS
from apps.rbac.services import permissions_for

from .models import Mcc, MccAssignment, MccCover, Mpp, MppAssignment, Responsibility

# A person can only hold an MPP if their role lets them do that job.
REQUIRED_PERMISSION = {
    Responsibility.FACILITATOR: "applications.create",
    Responsibility.AREA_MANAGER: "applications.approve_am",
}


def covers_running(day=None):
    """Covers in force on a day. The dates alone end a cover, so no job has to."""
    day = day or timezone.localdate()
    return MccCover.objects.filter(ended_at__isnull=True, starts_on__lte=day, ends_on__gte=day)


def covered_mccs(membership):
    """The MCCs someone works today for a colleague on leave."""
    absent = covers_running().filter(colleague=membership).values("absent")
    return MccAssignment.objects.filter(membership__in=absent, ended_at__isnull=True).values("mcc")


def accessible_mpps(membership, permissions):
    """Every query for MPP-owned data must start here, so a transfer moves access at once."""
    direct = Q(assignments__membership=membership, assignments__ended_at__isnull=True)
    allotted = Q(mcc__assignments__membership=membership, mcc__assignments__ended_at__isnull=True)
    covering = Q(mcc__in=covered_mccs(membership))
    # Someone given MCCs works those, even in a role that could see everything. A head,
    # given none, keeps the whole organization, and a cover only ever adds.
    has_mccs = MccAssignment.objects.filter(membership=membership, ended_at__isnull=True).exists()
    if "mpp.view_all" in permissions and not has_mccs:
        return Mpp.objects.all()
    return Mpp.objects.filter(direct | allotted | covering).distinct()


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
    covers = MccCover.objects.filter(
        Q(absent=membership) | Q(colleague=membership),
        ended_at__isnull=True,
        ends_on__gte=timezone.localdate(),
    )
    for cover in covers:
        end_cover(cover=cover, actor=actor)


class CoverError(Exception):
    pass


@transaction.atomic
def give_cover(*, absent, colleague, starts_on, ends_on, reason, actor):
    """Hand someone's MCCs to a colleague for some days. Both work them meanwhile."""
    from apps.notifications.services import notify

    if absent.pk == colleague.pk:
        raise CoverError("Choose someone other than the person who is away.")
    if ends_on < starts_on:
        raise CoverError("The last day must be on or after the first.")
    if ends_on < timezone.localdate():
        raise CoverError("These days are already over.")
    mccs = list(
        Mcc.objects.filter(assignments__membership=absent, assignments__ended_at__isnull=True)
        .order_by("code")
        .values_list("code", flat=True)
    )
    if not mccs:
        raise CoverError("This person holds no MCCs to hand over.")
    needed = APPROVAL_PERMISSIONS & permissions_for(absent)
    if not needed <= permissions_for(colleague):
        raise CoverError("This colleague cannot approve every stage the person away does.")
    clash = MccCover.objects.filter(
        absent=absent,
        colleague=colleague,
        ended_at__isnull=True,
        starts_on__lte=ends_on,
        ends_on__gte=starts_on,
    ).exists()
    if clash:
        raise CoverError("This colleague already covers this person on some of these days.")

    cover = MccCover.objects.create(
        absent=absent,
        colleague=colleague,
        starts_on=starts_on,
        ends_on=ends_on,
        reason=reason,
        given_by=actor,
    )
    record_event(
        "mcc.cover_given",
        actor=actor,
        target=cover,
        metadata={
            "absent": str(absent.id),
            "colleague": str(colleague.id),
            "starts_on": starts_on.isoformat(),
            "ends_on": ends_on.isoformat(),
            "reason": reason,
            "mccs": mccs,
        },
    )
    notify(
        [colleague],
        title=f"You cover {_name(absent)} from {_day(starts_on)} to {_day(ends_on)}",
        body=f"You work their MCCs ({', '.join(mccs)}) on those days, in your own role. "
        f"Reason: {reason}",
    )
    return cover


@transaction.atomic
def end_cover(*, cover, actor) -> bool:
    """Stop a cover early, or call off one that has not begun. The row stays as history."""
    from apps.notifications.services import notify

    cover = MccCover.objects.select_for_update().get(pk=cover.pk)
    if cover.ended_at or cover.ends_on < timezone.localdate():
        return False
    _end(cover, actor)
    record_event(
        "mcc.cover_ended",
        actor=actor,
        target=cover,
        metadata={"absent": str(cover.absent_id), "colleague": str(cover.colleague_id)},
    )
    notify(
        [cover.colleague],
        title=f"Your cover for {_name(cover.absent)} has ended",
        body="Their MCCs are no longer in your queue, unless you hold them yourself.",
    )
    return True


def _name(membership) -> str:
    return membership.user.full_name or membership.user.email


def _day(value) -> str:
    return f"{value.day} {value:%b}"
