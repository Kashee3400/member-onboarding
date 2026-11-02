"""
The bank and branch master, so a typed IFSC fills the passbook's bank and branch
without the phone going online. Loaded from the ERP's export, or any file with the
same columns.
"""

import csv
import io
import re
from collections import Counter

from django.db import transaction
from openpyxl import load_workbook
from rest_framework import exceptions

from apps.core.tenancy import get_current_organization_id

from .models import Bank, BankBranch

IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
COLUMNS = ("ifsc", "bank_name", "branch_name")
OPTIONAL_COLUMNS = ("address", "district", "bank_code", "branch_code", "is_active")
MAX_ROWS = 200_000
MAX_PROBLEMS = 50
BATCH_SIZE = 1000


def _text(value) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def _flag(value: str) -> bool:
    """A missing flag means active: most files list only branches in use."""
    return value.strip().lower() not in ("0", "false", "f", "no", "n", "inactive")


def _table(raw: bytes):
    if raw[:2] == b"PK":
        sheet = load_workbook(io.BytesIO(raw), read_only=True, data_only=True).active
        return sheet.iter_rows(values_only=True)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return csv.reader(io.StringIO(text))


def read_rows(raw: bytes) -> list[dict]:
    try:
        table = _table(raw)
        header = [_text(cell).lower() for cell in next(table)]
    except Exception as exc:
        raise exceptions.ValidationError({"file": ["Upload a CSV or Excel (.xlsx) file."]}) from exc

    missing = [column for column in COLUMNS if column not in header]
    if missing:
        raise exceptions.ValidationError({"file": [f"Missing columns: {', '.join(missing)}"]})

    present = (*COLUMNS, *(column for column in OPTIONAL_COLUMNS if column in header))
    positions = {column: header.index(column) for column in present}
    records = []
    for number, row in enumerate(table, start=2):
        record = dict.fromkeys(OPTIONAL_COLUMNS, "")
        record |= {
            column: _text(row[at] if at < len(row) else "") for column, at in positions.items()
        }
        if any(record.values()):
            records.append({**record, "row": number})
            if len(records) > MAX_ROWS:
                raise exceptions.ValidationError({"file": [f"At most {MAX_ROWS} rows per file."]})
    return records


def bank_named(name: str, banks: dict[str, Bank], erp_code: str = "") -> Bank:
    """Matched without regard to case, so one bank is not listed twice."""
    found = banks.get(name.lower())
    if found is None:
        found = Bank.objects.create(name=name, erp_code=erp_code)
        banks[name.lower()] = found
    return found


@transaction.atomic
def import_branches(records: list[dict]) -> dict:
    """
    Adds new branches and updates known ones, matched by IFSC. Rows that cannot be
    used are reported and skipped, so one bad line does not hold back the rest.
    """
    report = Counter()
    problems = []
    branches: dict[str, dict] = {}
    for record in records:
        ifsc = record["ifsc"].upper()
        reasons = []
        if not IFSC.match(ifsc):
            reasons.append("ifsc is not valid")
        if not record["bank_name"]:
            reasons.append("bank_name is empty")
        if not record["branch_name"]:
            reasons.append("branch_name is empty")
        if reasons:
            report["skipped"] += 1
            if len(problems) < MAX_PROBLEMS:
                problems.append({"row": record["row"], "problem": "; ".join(reasons)})
            continue
        if ifsc in branches:
            report["repeated"] += 1
        # A later row for the same IFSC wins, as it would if imported on its own.
        branches[ifsc] = {**record, "ifsc": ifsc}

    banks = {bank.name.lower(): bank for bank in Bank.objects.all()}
    known = set(BankBranch.objects.filter(ifsc__in=branches).values_list("ifsc", flat=True))
    organization_id = get_current_organization_id()
    BankBranch.objects.bulk_create(
        (
            BankBranch(
                organization_id=organization_id,
                bank=bank_named(record["bank_name"][:200], banks, record["bank_code"][:20]),
                name=record["branch_name"][:200],
                ifsc=ifsc,
                address=record["address"][:300],
                district=record["district"][:100],
                erp_code=record["branch_code"][:20],
                is_active=_flag(record["is_active"]),
            )
            for ifsc, record in branches.items()
        ),
        batch_size=BATCH_SIZE,
        update_conflicts=True,
        unique_fields=["organization", "ifsc"],
        update_fields=[
            "bank",
            "name",
            "address",
            "district",
            "erp_code",
            "is_active",
            "updated_at",
        ],
    )
    report["created"] = len(branches) - len(known)
    report["updated"] = len(known)
    return {
        "created": report["created"],
        "updated": report["updated"],
        "skipped": report["skipped"],
        "repeated": report["repeated"],
        "problems": problems,
    }


def by_ifsc(ifsc: str) -> BankBranch | None:
    """Only a branch in use, of a bank in use, fills a form."""
    return (
        BankBranch.objects.filter(ifsc=ifsc.strip().upper(), is_active=True, bank__is_active=True)
        .select_related("bank")
        .first()
    )
