"""
One person's own review steps, in place of what their roles give.

Roles decide by default, so nobody has to be set up one by one. An override narrows
or reshapes it for one person, within the stages they approve. A stage still needs
every one of its steps approved, so a step taken from someone must have someone else
to approve it on their MPPs, or their forms would wait at that stage for good.
"""

from django.db import transaction
from rest_framework import exceptions

from apps.audit.services import record_event
from apps.hierarchy.services import accessible_mpps
from apps.organizations.models import Membership
from apps.rbac.services import permissions_for, role_codes_for

from . import review_steps
from .models import StaffReviewSteps


def state(membership) -> dict:
    own = review_steps.custom_steps(membership)
    by_role = review_steps.role_steps(membership)
    return {
        "custom": own is not None,
        "steps": sorted(own if own is not None else by_role),
        "role_steps": sorted(by_role),
        "eligible": sorted(review_steps.eligible_steps(membership)),
        "approves_all": review_steps.acts_on_all(membership),
    }


def _mpp_ids(membership) -> set:
    return set(
        accessible_mpps(membership, permissions_for(membership)).values_list("pk", flat=True)
    )


def uncovered(membership, steps: set[str]) -> dict[str, int]:
    """
    Steps this person's roles give them, but `steps` leaves out, that nobody else
    can approve on some of their MPPs: step to how many MPPs. The admin, who may
    approve anything, does not count: forms should not wait on them.
    """
    dropped = review_steps.role_steps(membership) - steps
    if not dropped:
        return {}
    mine = _mpp_ids(membership)
    if not mine:
        return {}

    saved = review_steps.roles_by_step()
    others = []
    for other in Membership.objects.filter(is_active=True).exclude(pk=membership.pk):
        if review_steps.acts_on_all(other):
            continue
        own = review_steps.custom_steps(other)
        held = role_codes_for(other)
        their_steps = own if own is not None else review_steps.role_steps(other, saved)
        others.append((other, held, their_steps))

    result = {}
    reach = {}
    for stage in review_steps.approving_stages(membership):
        stage_roles = review_steps._stage_roles(stage)
        for step in dropped & review_steps.stage_steps(stage):
            covered = set()
            for other, held, their_steps in others:
                if not held & stage_roles or step not in their_steps:
                    continue
                if other.pk not in reach:
                    reach[other.pk] = _mpp_ids(other)
                covered |= reach[other.pk]
                if mine <= covered:
                    break
            if missing := len(mine - covered):
                result[step] = max(result.get(step, 0), missing)
    return result


@transaction.atomic
def save(membership, steps: list[str] | None, *, actor, confirm=False) -> dict:
    """Sets this person's own steps, or with None goes back to their roles."""
    if steps is None:
        StaffReviewSteps.objects.filter(membership=membership).delete()
        record_event("staff.review_steps_reset", actor=actor, target=membership)
        return state(membership)

    chosen = set(steps)
    if unknown := chosen - set(review_steps.STEP_KEYS):
        raise exceptions.ValidationError(
            {"steps": [f"Unknown steps: {', '.join(sorted(unknown))}."]}
        )
    if not review_steps.approving_stages(membership):
        raise exceptions.ValidationError(
            {"steps": ["This person approves at no stage. Give them an approver role first."]}
        )
    if outside := chosen - review_steps.eligible_steps(membership):
        titles = ", ".join(review_steps.TITLES[key] for key in sorted(outside))
        raise exceptions.ValidationError(
            {"steps": [f"Not a step of the stages they approve: {titles}."]}
        )

    gaps = uncovered(membership, chosen)
    if gaps and not confirm:
        raise StepsLeftUncovered(gaps)

    StaffReviewSteps.objects.update_or_create(
        membership=membership,
        defaults={"steps": sorted(chosen), "organization_id": membership.organization_id},
    )
    record_event(
        "staff.review_steps_set",
        actor=actor,
        target=membership,
        metadata={"steps": sorted(chosen), "left_uncovered": gaps},
    )
    return state(membership)


class StepsLeftUncovered(exceptions.APIException):
    status_code = 409
    default_code = "steps_left_uncovered"

    def __init__(self, gaps: dict[str, int]):
        lines = [
            f"{review_steps.TITLES[key]}: nobody else approves it on {count} of their MPPs"
            for key, count in sorted(gaps.items())
        ]
        super().__init__("Their forms would wait at this stage. " + "; ".join(lines) + ".")
        self.gaps = gaps
