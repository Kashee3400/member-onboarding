"""
Staff to and from a spreadsheet, in one layout both ways: what Export gives, Import
takes back. An import is checked first and then made all at once, so a file with a
mistake changes nothing. Facilitators come from the ERP and are never imported.
"""

import re
from io import BytesIO

from django.contrib.auth import get_user_model
from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from rest_framework import exceptions

from apps.accounts.password_views import issue_temporary_password
from apps.audit.services import record_event
from apps.branding.services import staff_email_problem
from apps.hierarchy.models import Mcc, MccAssignment, Mpp, MppAssignment, Responsibility
from apps.hierarchy.services import assign_mcc, assign_mpp
from apps.organizations.models import Membership

from .models import Role
from .serializers import MOBILE, NO_EMAIL_DOMAIN
from .services import permissions_for, set_membership_roles

COLUMNS = (
    ("organization", "Organization code, as on the portal", 14),
    ("full_name", "Full name as it should print on the form", 28),
    ("email", "Login email (or leave blank and give mobile)", 32),
    ("mobile", "10-digit mobile, optional", 14),
    ("role", "Role codes, comma separated: cs_legal, finance, area_manager, org_admin", 22),
    ("mcc_codes", "MCC codes they approve for, comma separated", 22),
    ("mpp_codes", "Area managers only: MPP codes, if not by MCC", 24),
    ("signs_as_head", "yes = their signature prints for CS & Legal or Finance (one each)", 16),
)
NAMES = tuple(name for name, _, _ in COLUMNS)
MAX_ROWS = 500
HEAD_STAGES = {
    "applications.approve_cs": "pending_cs",
    "applications.approve_finance": "pending_finance",
}
APPROVES = frozenset(
    {"applications.approve_am", "applications.approve_cs", "applications.approve_finance"}
)
_NO_EMAIL = ("@external.invalid", NO_EMAIL_DOMAIN)
_SPLIT = re.compile(r"[,\s;]+")


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _codes(value) -> list[str]:
    return [code for code in _SPLIT.split(_text(value)) if code]


def _by_code(objects) -> dict:
    """
    Each object under its code, and a numeric code also under its number: Excel
    drops leading zeros, so 5 in a sheet is MCC 005 in the masters.
    """
    found = {}
    for obj in objects:
        found[obj.code] = obj
        if obj.code.isdigit():
            found.setdefault(str(int(obj.code)), obj)
    return found


def _resolve(codes, found) -> tuple[list[str], list[str]]:
    """The masters' own codes for these, and the ones not found."""
    known, unknown = [], []
    for code in codes:
        obj = found.get(code) or (found.get(str(int(code))) if code.isdigit() else None)
        (known if obj else unknown).append(obj.code if obj else code)
    return known, unknown


# Export ------------------------------------------------------------------------------


def _sheet(rows) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Staff"
    head = PatternFill("solid", fgColor="1F4E78")
    for column, (name, help_text, width) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(1, column, name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head
        note = sheet.cell(2, column, help_text)
        note.font = Font(italic=True, color="666666", size=9)
        note.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.column_dimensions[cell.column_letter].width = width
    sheet.row_dimensions[2].height = 42
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "A3"
    choice = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    sheet.add_data_validation(choice)
    choice.add("H3:H1000")
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def export_staff(organization, *, template=False) -> bytes:
    if template:
        return _sheet([])
    from apps.applications.models import Signatory

    heads = set(Signatory.objects.values_list("membership_id", flat=True))
    mccs, mpps = {}, {}
    for membership_id, code in MccAssignment.objects.filter(ended_at__isnull=True).values_list(
        "membership_id", "mcc__code"
    ):
        mccs.setdefault(membership_id, []).append(code)
    for membership_id, code in MppAssignment.objects.filter(
        ended_at__isnull=True, responsibility=Responsibility.AREA_MANAGER
    ).values_list("membership_id", "mpp__code"):
        mpps.setdefault(membership_id, []).append(code)

    rows = []
    memberships = (
        Membership.objects.filter(is_active=True)
        .select_related("user")
        .prefetch_related("role_links__role")
        .order_by("user__full_name", "user__email")
    )
    for membership in memberships:
        email = membership.user.email
        rows.append(
            [
                organization.slug,
                membership.user.full_name,
                "" if email.endswith(_NO_EMAIL) else email,
                membership.mobile,
                ", ".join(sorted(link.role.code for link in membership.role_links.all())),
                ", ".join(sorted(mccs.get(membership.id, []))),
                ", ".join(sorted(mpps.get(membership.id, []))),
                "yes" if membership.id in heads else "",
            ]
        )
    return _sheet(rows)


# Import ------------------------------------------------------------------------------


def read_rows(content: bytes) -> list[dict]:
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any unreadable file gets the same answer
        raise exceptions.ValidationError({"file": ["This is not an Excel (.xlsx) file."]}) from exc
    sheet = book["Staff"] if "Staff" in book.sheetnames else book.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [_text(value).lower() for value in next(rows, ())]
    missing = [name for name in NAMES if name not in header]
    if missing:
        raise exceptions.ValidationError(
            {"file": [f"Missing columns: {', '.join(missing)}. Start from the template."]}
        )
    at = {name: header.index(name) for name in NAMES}
    records = []
    for number, values in enumerate(rows, start=2):
        record = {name: _text(values[at[name]]) if at[name] < len(values) else "" for name in NAMES}
        if not any(record.values()):
            continue
        # The template's second row explains each column.
        if number == 2 and record["full_name"].lower().startswith("full name"):
            continue
        record["row"] = number
        records.append(record)
    if len(records) > MAX_ROWS:
        raise exceptions.ValidationError({"file": [f"At most {MAX_ROWS} people in one file."]})
    return records


def _plan(records, organization) -> list[dict]:
    """Every row with what would happen to it, and its problems."""
    User = get_user_model()
    roles = {role.code: role for role in Role.objects.all()}
    mccs = _by_code(Mcc.objects.filter(is_active=True))
    mpps = _by_code(Mpp.objects.filter(is_active=True))
    here = {
        membership.user.email: membership
        for membership in Membership.objects.select_related("user")
    }
    mobiles = dict(Membership.objects.exclude(mobile="").values_list("mobile", "user__email"))
    seen_email, seen_mobile, heads = {}, {}, {}

    plans = []
    for record in records:
        problems, notes = [], []
        email = record["email"].lower()
        mobile = record["mobile"]
        codes = [code.lower() for code in _codes(record["role"])]
        plan = {
            "row": record["row"],
            "full_name": record["full_name"],
            "email": email,
            "mobile": mobile,
            "roles": codes,
            "mccs": _codes(record["mcc_codes"]),
            "mpps": _codes(record["mpp_codes"]),
            "head": record["signs_as_head"].lower() in ("yes", "y", "true", "1"),
        }

        if record["organization"] and record["organization"].lower() != organization.slug.lower():
            problems.append(
                f"This row is for {record['organization']}. Import it while working in that "
                "organization."
            )
        if not plan["full_name"]:
            problems.append("Give a full name.")
        if not email and not mobile:
            problems.append("Give an email, a mobile, or both.")
        if email:
            if problem := staff_email_problem(email):
                problems.append(problem)
            elif email in seen_email:
                problems.append(f"Same email as row {seen_email[email]}.")
            seen_email.setdefault(email, record["row"])
        if mobile:
            if not re.fullmatch(MOBILE, mobile):
                problems.append("The mobile must be 10 digits, starting 6 to 9.")
            elif mobile in seen_mobile:
                problems.append(f"Same mobile as row {seen_mobile[mobile]}.")
            elif mobiles.get(mobile) not in (None, email):
                problems.append("Someone in this organization already has this mobile.")
            seen_mobile.setdefault(mobile, record["row"])

        if "facilitator" in codes:
            plan["action"] = "skip"
            notes.append("Facilitators come from the ERP when they open the form. Left out.")
            plan.update(problems=[], notes=notes)
            plans.append(plan)
            continue
        if not codes:
            problems.append("Give at least one role.")
        if unknown := [code for code in codes if code not in roles]:
            problems.append(f"Unknown roles: {', '.join(unknown)}.")
        granted = set().union(*(roles[code].permissions for code in codes if code in roles))

        plan["mccs"], unknown = _resolve(plan["mccs"], mccs)
        if unknown:
            problems.append(f"Unknown MCC codes: {', '.join(unknown)}.")
        plan["mpps"], unknown = _resolve(plan["mpps"], mpps)
        if unknown:
            problems.append(f"Unknown MPP codes: {', '.join(unknown)}.")
        if plan["mccs"] and not granted & APPROVES:
            problems.append("Only someone who approves forms can be given MCCs.")
        if plan["mpps"] and "applications.approve_am" not in granted:
            problems.append("Only an Area Manager can be given MPPs.")
        if "applications.approve_am" in granted and not plan["mccs"] and not plan["mpps"]:
            notes.append("No MCC or MPP yet: they will see no forms until given some.")

        if plan["head"]:
            stages = [stage for permission, stage in HEAD_STAGES.items() if permission in granted]
            if not stages:
                notes.append("signs_as_head is only for CS & Legal and Finance. Ignored.")
                plan["head"] = False
            for stage in stages:
                if stage in heads:
                    problems.append(f"Row {heads[stage]} already signs for this team.")
                heads.setdefault(stage, record["row"])
            plan["head_stages"] = stages

        existing = here.get(email) if email else None
        if existing is not None:
            plan["action"] = "skip"
            notes.append("Already staff here. Left as it is.")
        elif email and User.objects.filter(email=email).exists():
            plan["action"] = "add"
            notes.append("Has an account in another organization: keeps their own password.")
        else:
            plan["action"] = "create"
        plan["problems"] = problems
        plan["notes"] = notes
        plans.append(plan)
    return plans


def preview(records, organization) -> dict:
    plans = _plan(records, organization)
    return {
        "rows": plans,
        "create": sum(1 for plan in plans if plan["action"] == "create"),
        "add": sum(1 for plan in plans if plan["action"] == "add"),
        "skip": sum(1 for plan in plans if plan["action"] == "skip"),
        "problems": sum(1 for plan in plans if plan["problems"]),
    }


@transaction.atomic
def import_staff(records, organization, *, actor) -> dict:
    from apps.applications.models import Signatory

    summary = preview(records, organization)
    if summary["problems"]:
        return {**summary, "credentials": []}

    User = get_user_model()
    roles = {role.code: role for role in Role.objects.all()}
    mccs = {mcc.code: mcc for mcc in Mcc.objects.all()}
    mpps = {mpp.code: mpp for mpp in Mpp.objects.all()}
    credentials = []
    for plan in summary["rows"]:
        if plan["action"] == "skip":
            continue
        email = plan["email"] or f"m-{plan['mobile']}{NO_EMAIL_DOMAIN}"
        user = User.objects.filter(email=email).first()
        password = ""
        if user is None:
            user = User.objects.create_user(email, None, full_name=plan["full_name"])
            password = issue_temporary_password(user)
        membership = Membership.objects.create(
            organization=organization, user=user, mobile=plan["mobile"]
        )
        set_membership_roles(membership, [roles[code] for code in plan["roles"]])
        for code in plan["mccs"]:
            assign_mcc(mcc=mccs[code], membership=membership, actor=actor)
        if "applications.approve_am" in permissions_for(membership):
            for code in plan["mpps"]:
                assign_mpp(
                    mpp=mpps[code],
                    membership=membership,
                    responsibility=Responsibility.AREA_MANAGER,
                    actor=actor,
                )
        for stage in plan.get("head_stages", []) if plan["head"] else []:
            Signatory.objects.update_or_create(stage=stage, defaults={"membership": membership})
        credentials.append(
            {
                "full_name": plan["full_name"],
                "email": plan["email"],
                "mobile": plan["mobile"],
                "roles": plan["roles"],
                "temporary_password": password,
            }
        )
    record_event(
        "staff.imported",
        actor=actor,
        metadata={
            "created": summary["create"],
            "added": summary["add"],
            "skipped": summary["skip"],
        },
    )
    return {**summary, "credentials": credentials}
