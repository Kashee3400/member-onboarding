"""
Loads plants, MCCs and MPPs from a spreadsheet, and where each MPP is: its state,
district, tehsil, village and hamlet, post office and PIN code. A file is all or
nothing: masters decide who can see what, so half an import would be worse than none.
"""

import re
from io import BytesIO

from django.db import transaction
from openpyxl import load_workbook
from rest_framework import exceptions

from .models import Bmc, District, Hamlet, Mcc, Mpp, Plant, Route, State, Tehsil, Village

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
# The MPP's place. A blank cell leaves what is there, so a file need not carry all of it.
PLACE_COLUMNS = (
    "state_name",
    "district_code",
    "district_name",
    "tehsil_code",
    "tehsil_name",
    "hamlet_name",
    "post_office",
    "pincode",
)
OPTIONAL_COLUMNS = (*OPTIONAL_COLUMNS, *PLACE_COLUMNS)
MAX_ROWS = 5000
_VILLAGE = re.compile(r"^\d{8}$")
_TWO_DIGITS = re.compile(r"^(\d{2})?$")
_PINCODE = re.compile(r"^([1-9]\d{5})?$")
_PLACE_CODE = re.compile(r"^[0-9A-Za-z]{1,10}$")


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
    parents = {}

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
        reasons += _place_reasons(record, parents)

        seen_codes.add(record["mpp_code"])
        seen_villages.add(village_number)
        seen_internal.add(internal)
        if reasons:
            problems.append({"row": record["row"], "problem": "; ".join(reasons)})
    return problems


def _has_place(record: dict) -> bool:
    return bool(record["district_code"] or record["tehsil_code"])


def _place_reasons(record: dict, parents: dict) -> list[str]:
    """A place chain must be whole, and a district or tehsil sit under one parent only."""
    reasons = []
    if not _PINCODE.match(record["pincode"]):
        reasons.append("pincode must be 6 digits")
    if not _has_place(record):
        if record["hamlet_name"] and not record["hamlet_code"]:
            reasons.append("a hamlet_name needs a hamlet_code")
        return reasons

    for column in ("state_code", "district_code", "tehsil_code"):
        if not record[column]:
            reasons.append(f"{column} is empty")
    for column in ("district_code", "tehsil_code"):
        if record[column] and not _PLACE_CODE.match(record[column]):
            reasons.append(f"{column} must be up to 10 letters or digits")
    if record["hamlet_name"] and not record["hamlet_code"]:
        reasons.append("a hamlet_name needs a hamlet_code")
    if reasons:
        return reasons

    for level, parent in (
        (("district", record["district_code"]), record["state_code"]),
        (("tehsil", record["tehsil_code"]), record["district_code"]),
        (("village", record["village_code"]), record["tehsil_code"]),
    ):
        if parents.setdefault(level, parent) != parent:
            reasons.append(f"{level[0]} {level[1]} sits under two different parents in this file")
    return reasons


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


def _upsert(model, cache, key, name, lookup, parent=None, new_name=""):
    """Names in the file win, and a blank one keeps the name already there."""
    if key in cache:
        return cache[key]
    item = model.objects.filter(**lookup).first()
    changes = {**(parent or {}), **({"name": name} if name else {})}
    if item is None:
        item = model.objects.create(
            **lookup, **(parent or {}), name=name or new_name or lookup["code"]
        )
    elif any(getattr(item, field) != value for field, value in changes.items()):
        for field, value in changes.items():
            setattr(item, field, value)
        item.save()
    cache[key] = item
    return item


def _place(record: dict, cache: dict):
    """
    The MPP's village and hamlet. A row without a place still links to a village and
    hamlet already in the masters under its codes.
    """
    village_code, hamlet_code = record["village_code"], record["hamlet_code"]
    if not _has_place(record):
        village = cache.get(("village", village_code))
        village = village or Village.objects.filter(code=village_code).first()
        hamlet = None
        if village and hamlet_code:
            hamlet = Hamlet.objects.filter(village=village, code=hamlet_code).first()
        return village, hamlet

    state_code, district_code, tehsil_code = (
        record["state_code"],
        record["district_code"],
        record["tehsil_code"],
    )
    state = _upsert(State, cache, ("state", state_code), record["state_name"], {"code": state_code})
    district = _upsert(
        District,
        cache,
        ("district", district_code),
        record["district_name"],
        {"code": district_code},
        {"state": state},
    )
    tehsil = _upsert(
        Tehsil,
        cache,
        ("tehsil", tehsil_code),
        record["tehsil_name"],
        {"code": tehsil_code},
        {"district": district},
    )
    # Without a village name, the MPP's is the best guess, as the form always used it.
    village = _upsert(
        Village,
        cache,
        ("village", village_code),
        record["village_name"],
        {"code": village_code},
        {"tehsil": tehsil},
        new_name=record["mpp_name"],
    )
    hamlet = None
    if hamlet_code:
        hamlet = _upsert(
            Hamlet,
            cache,
            ("hamlet", village_code, hamlet_code),
            record["hamlet_name"],
            {"village": village, "code": hamlet_code},
        )
    return village, hamlet


@transaction.atomic
def import_masters(records) -> dict:
    problems = _problems(records) or _conflicts(records)
    if problems:
        return {"created": 0, "updated": 0, "problems": problems}

    created = updated = 0
    plants, mccs, bmcs, routes, places = {}, {}, {}, {}, {}
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
        village, hamlet = _place(record, places)
        defaults = {
            "mcc": mccs[mcc_code],
            "route": routes.get(route_code),
            "name": record["mpp_name"],
            "village_code": record["village_code"],
            "village_name": record["village_name"],
            "source_code": record["mpp_internal_code"],
            "state_code": record["state_code"],
            "hamlet_code": record["hamlet_code"],
            "village": village,
            "hamlet": hamlet,
        }
        defaults |= {key: record[key] for key in ("post_office", "pincode") if record[key]}
        _, was_created = Mpp.objects.update_or_create(code=record["mpp_code"], defaults=defaults)
        created += was_created
        updated += not was_created

    return {"created": created, "updated": updated, "problems": []}
