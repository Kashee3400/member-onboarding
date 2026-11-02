"""
Loads plants, MCCs and MPPs from a spreadsheet. A file is all or nothing: masters
decide who can see what, so half an import would be worse than none.
"""

import re
from io import BytesIO

from django.db import transaction
from openpyxl import load_workbook
from rest_framework import exceptions

from .models import Bmc, Mcc, Mpp, Plant, Route

COLUMNS = (
    "plant_code",
    "plant_name",
    "mcc_code",
    "mcc_name",
    "mpp_code",
    "mpp_internal_code",
    "mpp_name",
    "village_code",
)
# Without these two, an MPP takes the organization's defaults.
CODE_PARTS = ("state_code", "hamlet_code")
OPTIONAL_COLUMNS = (
    *CODE_PARTS,
    "bmc_code",
    "bmc_name",
    "route_code",
    "route_name",
    "village_name",
)
MAX_ROWS = 5000
_VILLAGE = re.compile(r"^\d{8}$")
_TWO_DIGITS = re.compile(r"^(\d{2})?$")


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _has_no_mpp(record: dict) -> bool:
    """An MCC, BMC or route with no MPPs yet still belongs in the masters."""
    return not any(record[column] for column in ("mpp_code", "mpp_name", "village_code"))


def read_rows(raw: bytes) -> list[dict]:
    try:
        sheet = load_workbook(BytesIO(raw), read_only=True, data_only=True).active
        rows = sheet.iter_rows(values_only=True)
        header = [_text(cell).lower() for cell in next(rows)]
    except Exception as exc:
        raise exceptions.ValidationError({"file": ["Upload an Excel (.xlsx) file."]}) from exc

    missing = [column for column in COLUMNS if column not in header]
    if missing:
        raise exceptions.ValidationError({"file": [f"Missing columns: {', '.join(missing)}"]})

    present = (*COLUMNS, *(column for column in OPTIONAL_COLUMNS if column in header))
    positions = {column: header.index(column) for column in present}
    records = []
    for number, row in enumerate(rows, start=2):
        record = dict.fromkeys(OPTIONAL_COLUMNS, "")
        record |= {column: _text(row[at]) for column, at in positions.items()}
        if any(record.values()):
            records.append({**record, "row": number})
    if len(records) > MAX_ROWS:
        raise exceptions.ValidationError({"file": [f"At most {MAX_ROWS} rows per file."]})
    return records


def _problems(records) -> list[dict]:
    problems = []
    seen_codes, seen_villages, seen_internal = set(), set(), set()

    for record in records:
        reasons = []
        for column in ("plant_code", "plant_name", "mcc_code", "mcc_name"):
            if not record[column]:
                reasons.append(f"{column} is empty")
        for code, name in (("bmc_code", "bmc_name"), ("route_code", "route_name")):
            if record[code] and not record[name]:
                reasons.append(f"{name} is empty")
        if record["route_code"] and not record["bmc_code"]:
            reasons.append("a route needs a bmc_code")
        if _has_no_mpp(record):
            if reasons:
                problems.append({"row": record["row"], "problem": "; ".join(reasons)})
            continue

        for column in ("mpp_code", "mpp_name"):
            if not record[column]:
                reasons.append(f"{column} is empty")
        if not _VILLAGE.match(record["village_code"]):
            reasons.append("village_code must be 8 digits")
        for column in CODE_PARTS:
            if not _TWO_DIGITS.match(record[column]):
                reasons.append(f"{column} must be 2 digits")
        if record["mpp_code"] in seen_codes:
            reasons.append("mpp_code is repeated in this file")
        village_number = (record["village_code"], record["hamlet_code"])
        if village_number in seen_villages:
            reasons.append("village_code and hamlet_code are repeated in this file")
        internal = record["mpp_internal_code"]
        if internal and internal in seen_internal:
            reasons.append("mpp_internal_code is repeated in this file")

        seen_codes.add(record["mpp_code"])
        seen_villages.add(village_number)
        seen_internal.add(internal)
        if reasons:
            problems.append({"row": record["row"], "problem": "; ".join(reasons)})
    return problems


def _conflicts(records) -> list[dict]:
    """An MPP may keep its own village and internal code, but not take another's."""
    existing = list(Mpp.objects.values("code", "village_code", "hamlet_code", "source_code"))
    village_owner = {(mpp["village_code"], mpp["hamlet_code"]): mpp["code"] for mpp in existing}
    internal_owner = {mpp["source_code"]: mpp["code"] for mpp in existing if mpp["source_code"]}

    problems = []
    for record in records:
        if _has_no_mpp(record):
            continue
        code = record["mpp_code"]
        if village_owner.get((record["village_code"], record["hamlet_code"]), code) != code:
            problems.append(
                {"row": record["row"], "problem": "village_code belongs to another MPP"}
            )
        if internal_owner.get(record["mpp_internal_code"], code) != code:
            problems.append(
                {"row": record["row"], "problem": "mpp_internal_code belongs to another MPP"}
            )
    return problems


@transaction.atomic
def import_masters(records) -> dict:
    problems = _problems(records) or _conflicts(records)
    if problems:
        return {"created": 0, "updated": 0, "problems": problems}

    created = updated = 0
    plants, mccs, bmcs, routes = {}, {}, {}, {}
    for record in records:
        plant_code = record["plant_code"]
        if plant_code not in plants:
            plants[plant_code], _ = Plant.objects.update_or_create(
                code=plant_code, defaults={"name": record["plant_name"]}
            )
        mcc_code = record["mcc_code"]
        if mcc_code not in mccs:
            mccs[mcc_code], _ = Mcc.objects.update_or_create(
                code=mcc_code,
                defaults={"name": record["mcc_name"], "plant": plants[plant_code]},
            )
        bmc_code = record["bmc_code"]
        if bmc_code and bmc_code not in bmcs:
            bmcs[bmc_code], _ = Bmc.objects.update_or_create(
                code=bmc_code, defaults={"name": record["bmc_name"], "mcc": mccs[mcc_code]}
            )
        route_code = record["route_code"]
        if route_code and route_code not in routes:
            routes[route_code], _ = Route.objects.update_or_create(
                code=route_code, defaults={"name": record["route_name"], "bmc": bmcs[bmc_code]}
            )
        if _has_no_mpp(record):
            continue
        _, was_created = Mpp.objects.update_or_create(
            code=record["mpp_code"],
            defaults={
                "mcc": mccs[mcc_code],
                "route": routes.get(route_code),
                "name": record["mpp_name"],
                "village_code": record["village_code"],
                "village_name": record["village_name"],
                "source_code": record["mpp_internal_code"],
                "state_code": record["state_code"],
                "hamlet_code": record["hamlet_code"],
            },
        )
        created += was_created
        updated += not was_created

    return {"created": created, "updated": updated, "problems": []}
