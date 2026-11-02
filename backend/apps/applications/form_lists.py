"""
The form's dropdown lists, as each organization keeps them.

An organization starts with the values in form.py, under the same codes, so forms
saved before the lists existed read the same. A value is never removed: it is
retired, which keeps it readable on old forms and printouts but off new ones.
"""

import re

from django.db import transaction
from rest_framework import exceptions

from apps.core.tenancy import get_current_organization_id

from . import form
from .form_hindi import OPTION_LABELS
from .models import FormOption

LISTS = {
    "gender": ("Gender", "The applicant and each household member"),
    "relation_type": ("Father or husband", "Whose name the applicant gives after her own"),
    "education": ("Education", "The applicant's schooling"),
    "category": ("Category", "The applicant's social category"),
    "family_status": ("Family status", "BPL or APL"),
    "family_relation": ("Household relation", "How each household member is related"),
    "nominee_relation": ("Nominee relation", "How the nominee is related to the applicant"),
}
MAX_LABEL = 100


def _seed(missing: set[str]) -> None:
    FormOption.objects.bulk_create(
        (
            FormOption(
                organization_id=get_current_organization_id(),
                list_key=key,
                value=option["value"],
                label=option["label"],
                label_hi=OPTION_LABELS.get(option["value"], option["label"]),
                position=position,
            )
            for key in sorted(missing)
            for position, option in enumerate(form.OPTION_LISTS[key])
        ),
        ignore_conflicts=True,
    )


def rows() -> list[FormOption]:
    """Every option, in order. A list seen for the first time gets its usual values."""
    found = list(FormOption.objects.all())
    missing = set(LISTS) - {row.list_key for row in found}
    if missing:
        _seed(missing)
        found = list(FormOption.objects.all())
    return found


def _serialized(row: FormOption) -> dict:
    return {
        "value": row.value,
        "label": row.label,
        "label_hi": row.label_hi,
        "active": row.is_active,
    }


def by_list() -> dict[str, list[dict]]:
    lists = {key: [] for key in LISTS}
    for row in rows():
        if row.list_key in lists:
            lists[row.list_key].append(_serialized(row))
    return lists


def schema() -> dict:
    return form.schema_with(by_list())


def choices() -> dict[str, set[str]]:
    """The values each list offers today, which is what a new answer must be."""
    return {
        key: {option["value"] for option in options if option["active"]}
        for key, options in by_list().items()
    }


def labels() -> dict[str, dict[str, str]]:
    """English labels of every value, retired ones too, for printing old forms."""
    return {
        key: {option["value"]: option["label"] for option in options}
        for key, options in by_list().items()
    }


def overview() -> list[dict]:
    lists = by_list()
    return [
        {"key": key, "title": title, "description": description, "options": lists[key]}
        for key, (title, description) in LISTS.items()
    ]


def _new_value(label: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:30] or "option"
    value, number = base, 2
    while value in taken:
        value, number = f"{base}_{number}", number + 1
    return value


def _check(key: str, options: list[dict], existing: dict, female_only: bool) -> None:
    sent = [option.get("value") for option in options if option.get("value")]
    unknown = [value for value in sent if value not in existing]
    if unknown:
        raise exceptions.ValidationError({"options": [f"{unknown[0]} is not in this list."]})
    if len(set(sent)) != len(sent):
        raise exceptions.ValidationError({"options": ["A value appears twice."]})
    if set(existing) - set(sent):
        raise exceptions.ValidationError(
            {"options": ["Values cannot be removed, because saved forms use them. Retire them."]}
        )
    names = [option["label"].strip().lower() for option in options]
    if len(set(names)) != len(names):
        raise exceptions.ValidationError({"options": ["Two options have the same name."]})
    if not any(option["is_active"] for option in options):
        raise exceptions.ValidationError({"options": ["Keep at least one option in use."]})
    retired = {option.get("value") for option in options if not option["is_active"]}
    if key == "gender" and female_only and "female" in retired:
        raise exceptions.ValidationError(
            {"options": ["Membership is open to women only, so Female must stay in use."]}
        )


@transaction.atomic
def save(key: str, options: list[dict], *, female_only: bool) -> None:
    """
    Replaces one list's wording and order. Every saved value must be sent back, so a
    value forms depend on cannot disappear; one without a value is new.
    """
    if key not in LISTS:
        raise exceptions.NotFound("No such list.")
    rows()
    existing = {
        row.value: row for row in FormOption.objects.select_for_update().filter(list_key=key)
    }
    _check(key, options, existing, female_only)

    taken = set(existing)
    for position, option in enumerate(options):
        label, label_hi = option["label"].strip(), option["label_hi"].strip()
        row = existing.get(option.get("value") or "")
        if row is None:
            value = _new_value(label, taken)
            taken.add(value)
            FormOption.objects.create(
                list_key=key,
                value=value,
                label=label,
                label_hi=label_hi,
                position=position,
                is_active=option["is_active"],
            )
            continue
        row.label, row.label_hi = label, label_hi
        row.position, row.is_active = position, option["is_active"]
        row.save(update_fields=["label", "label_hi", "position", "is_active", "updated_at"])
