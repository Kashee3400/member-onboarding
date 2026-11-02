"""
A checklist for each review step, set by the organization. A reviewer ticks every line
before approving the step, and the ticked lines are kept with the approval as proof of
what was checked. A step with no lines has no checklist.
"""

from django.conf import settings
from django.db import transaction
from rest_framework import exceptions

from apps.core.exceptions import Conflict

from . import review_settings, review_steps
from .models import ReviewCheck, ReviewSettings, StepCheckTick

MAX_CHECKS = 10

# Offered until an organization edits its own checklists.
DEFAULT_CHECKS = {
    "member": (
        "Aadhaar number matches the card photo",
        "Name, father / husband name and date of birth match the Aadhaar card",
        "Member photo is clear and of the applicant",
        "Signature or thumbprint is present and clear",
    ),
    "address": (
        "Address matches the Aadhaar card",
        "Mobile number is the member's own",
    ),
    "milk": (
        "Animal counts match what the member keeps",
        "Milk production and home use are realistic for those animals",
    ),
    "bank": (
        "Name matches the passbook",
        "Account number and IFSC match the passbook photo",
        "Passbook photo is clear and readable",
    ),
    "household": (
        "Every household member is listed with age and relation",
        "No household member is already a member",
    ),
    "nominee": (
        "Nominee name, relation and date of birth are filled in",
        "A guardian is named if the nominee is under 18",
        "The member accepted the declarations",
    ),
    "village": (
        "MPP, village and hamlet are right for the member",
        "Location on the map is in the member's village",
    ),
    "fee": (
        "Amount matches the member fee",
        "Payment slip shows the same amount and reference",
    ),
}


def _seed() -> None:
    """The default checklists, once per organization."""
    found = review_settings.current()
    if found.checks_seeded or not settings.SEED_REVIEW_CHECKS:
        return
    with transaction.atomic():
        locked = ReviewSettings.objects.select_for_update().get(pk=found.pk)
        if locked.checks_seeded:
            return
        ReviewCheck.objects.bulk_create(
            ReviewCheck(organization_id=locked.organization_id, step=step, text=text, position=n)
            for step, texts in DEFAULT_CHECKS.items()
            for n, text in enumerate(texts)
        )
        locked.checks_seeded = True
        locked.save(update_fields=["checks_seeded", "updated_at"])


def by_step() -> dict[str, list[str]]:
    _seed()
    checks = {key: [] for key in review_steps.STEP_KEYS}
    for step, text in ReviewCheck.objects.values_list("step", "text"):
        if step in checks:
            checks[step].append(text)
    return checks


@transaction.atomic
def save(checks: dict[str, list[str]]) -> None:
    """The checklists are sent whole: a step left out has none."""
    found = review_settings.current()
    ReviewCheck.objects.all().delete()
    ReviewCheck.objects.bulk_create(
        ReviewCheck(organization_id=found.organization_id, step=step, text=text, position=n)
        for step in review_steps.STEP_KEYS
        for n, text in enumerate(checks.get(step, []))
    )
    found.checks_seeded = True
    found.save(update_fields=["checks_seeded", "updated_at"])


def _ticks(application, user) -> dict[str, set[str]]:
    ticked = {key: set() for key in review_steps.STEP_KEYS}
    rows = StepCheckTick.objects.filter(
        application=application, revision=application.revision, user=user
    ).values_list("step", "text")
    for step, text in rows:
        ticked.setdefault(step, set()).add(text)
    return ticked


def ticked(application, user, step: str) -> list[str]:
    """This person's ticks on a step, in checklist order. A reworded check is unticked."""
    mine = _ticks(application, user)[step]
    return [text for text in by_step()[step] if text in mine]


def tick(application, *, user, step: str, text: str, on: bool) -> list[str]:
    if step not in review_steps.actionable(application, user.active_membership):
        raise Conflict("This step is not open for you to check.")
    if text not in by_step()[step]:
        raise exceptions.ValidationError({"text": ["This is not on the step's checklist."]})
    found = StepCheckTick.objects.filter(
        application=application,
        revision=application.revision,
        step=step,
        user=user,
        text=text,
    )
    if not on:
        found.delete()
    elif not found.exists():
        # A double click can race here; the unique constraint keeps one row.
        StepCheckTick.objects.bulk_create(
            [
                StepCheckTick(
                    organization_id=application.organization_id,
                    application=application,
                    revision=application.revision,
                    step=step,
                    text=text,
                    user=user,
                )
            ],
            ignore_conflicts=True,
        )
    return ticked(application, user, step)


def proof(application, user, steps) -> dict[str, list[str]]:
    """What each step's approval records, or why it cannot be approved yet."""
    checks = by_step()
    mine = _ticks(application, user)
    unticked = [
        key for key in review_steps.STEP_KEYS if key in steps and set(checks[key]) - mine[key]
    ]
    if unticked:
        titles = ", ".join(review_steps.TITLES[key] for key in unticked)
        raise exceptions.ValidationError(
            {"checks": [f"Tick every check of {titles} before approving."]}
        )
    return {key: checks[key] for key in steps}


def with_checks(steps: list[dict], application, user) -> list[dict]:
    """Each step's checklist, and what this person has ticked on it."""
    checks = by_step()
    mine = _ticks(application, user) if user else {}
    return [
        {
            **step,
            "checks": checks[step["key"]],
            "ticked": [text for text in checks[step["key"]] if text in mine.get(step["key"], ())],
        }
        for step in steps
    ]
