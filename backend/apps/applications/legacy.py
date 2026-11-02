"""
Members who joined before this system.

Without them, serial numbers would start again at 0001 and collide with codes
already printed on members' forms and used in SAP, and someone who is already a
member could apply again. Aadhaar numbers are never stored here, only their keyed
index, which is enough to spot a duplicate.
"""

import csv
import re
from collections import Counter

from django.db import transaction

from apps.core import crypto
from apps.hierarchy.models import Mpp

from .form import is_valid_aadhaar
from .models import LegacyMember, Sequence

TR_CODE = re.compile(r"^(\d{2})(\d{8})(\d{2})(\d{4})$")
BATCH_SIZE = 1000
MAX_FORM_GAP = 1000


def aadhaar_index(number: str, organization_id) -> str:
    return crypto.blind_index(number, f"aadhaar:{organization_id}")


def serial_key(state_code: str, village_code: str, hamlet_code: str) -> str:
    return f"member_serial:{state_code}:{village_code}:{hamlet_code}"


def _flag(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "t", "yes")


def _form_number(value: str, prefix: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", value.strip(), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _last_real_form_number(numbers: list[int]) -> tuple[int, int]:
    """
    Forms are numbered in order, so a few numbers far above the rest are mistyped.
    Trusting one would leave every new form far from the real series. At most one in
    a hundred is set aside, so a short or patchy history is taken as it is.
    """
    ordered = sorted(set(numbers))
    allowed = len(ordered) // 100
    dropped = 0
    while dropped < allowed and len(ordered) > 1 and ordered[-1] - ordered[-2] > MAX_FORM_GAP:
        ordered.pop()
        dropped += 1
    return (ordered[-1] if ordered else 0), dropped


def _raise_sequence(organization_id, key: str, value: int) -> None:
    """Only ever upward, so a repeated import cannot hand out a used number."""
    sequence, _ = Sequence.objects.select_for_update().get_or_create(
        organization_id=organization_id, key=key
    )
    if sequence.value < value:
        sequence.value = value
        sequence.save(update_fields=["value", "updated_at"])


@transaction.atomic
def import_legacy_members(path, *, organization_id, form_prefix: str) -> dict:
    report = Counter()
    highest_serial: dict[tuple[str, str, str], int] = {}
    form_numbers: list[int] = []
    records: dict[str, LegacyMember] = {}
    mpps = dict(Mpp.objects.exclude(source_code="").values_list("source_code", "id"))

    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            report["rows"] += 1
            tr_code = (row.get("member_tr_code") or "").strip()
            if not tr_code:
                report["without_code"] += 1
                continue

            match = TR_CODE.match(tr_code)
            if match:
                state_code, village, hamlet_code, serial = match.groups()
                key = (state_code, village, hamlet_code)
                highest_serial[key] = max(highest_serial.get(key, 0), int(serial))
            else:
                # Kept anyway: an unusual code is still a code that must not be reissued.
                report["unusual_code"] += 1

            aadhaar = (row.get("aadhar_no") or "").strip()
            index = ""
            if is_valid_aadhaar(aadhaar):
                index = aadhaar_index(aadhaar, organization_id)
            elif aadhaar:
                report["invalid_aadhaar"] += 1
            else:
                report["without_aadhaar"] += 1

            mobile = re.sub(r"\D", "", row.get("mobile_no") or "")[-10:]
            mobile_index = (
                crypto.blind_index(mobile, f"mobile:{organization_id}") if len(mobile) == 10 else ""
            )

            form_number = _form_number(row.get("application_no") or "", form_prefix)
            if form_number:
                form_numbers.append(form_number)

            is_active = _flag(row.get("is_active") or "")
            is_default = _flag(row.get("is_default") or "")
            existing = records.get(tr_code)
            # A code can appear on several rows. The default, active one describes it.
            if existing is None or (is_active and is_default):
                records[tr_code] = LegacyMember(
                    organization_id=organization_id,
                    tr_code=tr_code,
                    erp_member_code=(row.get("member_code") or "").strip(),
                    full_name=(row.get("member_name") or "").strip()[:200],
                    mpp_id=mpps.get((row.get("mpp_code") or "").strip()),
                    aadhaar_index=index or (existing.aadhaar_index if existing else ""),
                    mobile_index=mobile_index or (existing.mobile_index if existing else ""),
                    is_active=is_active or bool(existing and existing.is_active),
                )
            else:
                existing.aadhaar_index = existing.aadhaar_index or index
                existing.mobile_index = existing.mobile_index or mobile_index
                existing.is_active = existing.is_active or is_active

    LegacyMember.objects.bulk_create(
        records.values(),
        batch_size=BATCH_SIZE,
        update_conflicts=True,
        unique_fields=["organization", "tr_code"],
        update_fields=[
            "erp_member_code",
            "full_name",
            "mpp",
            "aadhaar_index",
            "mobile_index",
            "is_active",
            "updated_at",
        ],
    )

    for (state_code, village, hamlet_code), serial in highest_serial.items():
        _raise_sequence(organization_id, serial_key(state_code, village, hamlet_code), serial)
    highest_form, form_typos = _last_real_form_number(form_numbers)
    if highest_form:
        _raise_sequence(organization_id, "form_number", highest_form)

    report["members"] = len(records)
    report["villages"] = len({village for _, village, _ in highest_serial})
    report["highest_form_number"] = highest_form
    report["form_number_typos"] = form_typos
    report["active"] = sum(1 for record in records.values() if record.is_active)
    report["without_mpp"] = sum(1 for record in records.values() if record.mpp_id is None)
    return dict(report)


def existing_code_taken(tr_code: str) -> bool:
    return LegacyMember.objects.filter(tr_code=tr_code).exists()
