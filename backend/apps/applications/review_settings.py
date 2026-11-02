"""
What an organization can tune about review: when a waiting form counts as late, and
the ready-made reasons a reviewer can pick when sending a form back.
"""

from django.db import transaction

from . import form, review_steps
from .models import RejectReason, ReviewSettings

# Offered until an organization edits its own list.
DEFAULT_REASONS = (
    ("Name does not match the Aadhaar card", "applicant", ["applicant.full_name"]),
    ("Date of birth does not match the Aadhaar card", "applicant", ["applicant.date_of_birth"]),
    (
        "Father / husband name does not match the Aadhaar card",
        "applicant",
        ["applicant.relation_name"],
    ),
    ("Aadhaar photo is unclear or cut off", "applicant", []),
    ("Member photo is unclear", "applicant", []),
    ("Member signature is missing or unclear", "applicant", []),
    ("Mobile number is wrong", "address", ["address.mobile"]),
    ("Address is incomplete", "address", ["address.post_office", "address.pincode"]),
    (
        "Milk figures do not look right",
        "animals",
        ["animals.production_lpd", "animals.consumption_lpd"],
    ),
    ("Name does not match the passbook", "bank", ["bank.holder_name"]),
    ("IFSC does not match the passbook", "bank", ["bank.ifsc"]),
    ("Passbook photo is unclear", "bank", []),
    ("Household members are missing", "family", []),
    (
        "Nominee details are incomplete",
        "nominee",
        ["nominee.name", "nominee.relation", "nominee.date_of_birth"],
    ),
    ("Payment slip is missing or does not match", "payment", []),
)

SECTIONS = tuple(section for step in review_steps.STEPS for section in step.sections)
FIELD_PATHS = frozenset(
    f"{section['key']}.{field['key']}"
    for section in form.FORM_SCHEMA["sections"]
    for field in section["fields"]
)
_STEP_OF = {section: step.key for step in review_steps.STEPS for section in step.sections}


def current() -> ReviewSettings:
    """Created with the default reasons the first time, so an emptied list stays empty."""
    with transaction.atomic():
        found, created = ReviewSettings.objects.get_or_create()
        if created:
            RejectReason.objects.bulk_create(
                RejectReason(
                    organization_id=found.organization_id,
                    text=text,
                    section=section,
                    fields=fields,
                    position=position,
                )
                for position, (text, section, fields) in enumerate(DEFAULT_REASONS)
            )
    return found


def overdue_days() -> int:
    return current().overdue_days


def reject_reasons() -> list[RejectReason]:
    current()
    return list(RejectReason.objects.all())


def field_errors(section: str, fields: list[str]) -> list[str]:
    """
    A reason may mark only fields of its own review step: whoever is offered it can
    send back that step, and nothing else.
    """
    errors = []
    for path in fields:
        if path not in FIELD_PATHS:
            errors.append(f"{path} is not a field on the form.")
        elif _STEP_OF.get(path.split(".")[0]) != _STEP_OF.get(section):
            errors.append(f"{path} is not part of the step this reason belongs to.")
    return errors


def serialized(reasons) -> list[dict]:
    return [
        {"text": reason.text, "section": reason.section, "fields": reason.fields}
        for reason in reasons
    ]


def sections() -> list[dict]:
    """Each section a reason can belong to, with the fields it may mark."""
    schema = {section["key"]: section for section in form.FORM_SCHEMA["sections"]}
    rows = []
    for step in review_steps.STEPS:
        markable = [
            {"path": f"{key}.{field['key']}", "label": field["label"]}
            for key in step.sections
            if key in schema
            for field in schema[key]["fields"]
        ]
        for key in step.sections:
            title = schema[key]["title"] if key in schema else step.title
            rows.append({"key": key, "title": title, "step": step.title, "fields": markable})
    return rows


@transaction.atomic
def save(*, overdue_days: int, reasons: list[dict]) -> ReviewSettings:
    found = current()
    found.overdue_days = overdue_days
    found.save(update_fields=["overdue_days", "updated_at"])
    RejectReason.objects.all().delete()
    RejectReason.objects.bulk_create(
        RejectReason(
            organization_id=found.organization_id,
            text=reason["text"],
            section=reason["section"],
            fields=list(dict.fromkeys(reason["fields"])),
            position=position,
        )
        for position, reason in enumerate(reasons)
    )
    return found
