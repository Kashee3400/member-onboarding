"""
The home page's numbers. Each block appears only for those it is meant for, so a
role sees its own work first and nothing it cannot act on or read.
"""

from datetime import timedelta

from django.db.models import Count, IntegerField, Q, Sum
from django.db.models.fields.json import KT
from django.db.models.functions import Cast, TruncDate
from django.utils import timezone

from apps.documents.services import OWN_SIGNATURE_PERMISSIONS, current_signature
from apps.hierarchy.models import Mcc, MccAssignment
from apps.organizations.models import Membership
from apps.rbac.catalog import APPROVAL_PERMISSIONS
from apps.rbac.services import role_codes_for

from . import review_settings, review_steps, services
from .models import (
    Application,
    ApplicationStepApproval,
    LegacyMember,
    Member,
    ReviewStepAccess,
    Signatory,
    Status,
)

TREND_DAYS = 14


def _my_queue(membership, forms) -> dict:
    """Forms with a step this person can approve now, read in as few queries as possible."""
    held = role_codes_for(membership)
    by_step = review_steps.roles_by_step()
    mine_at = {}
    for status in review_steps.STAGE_PERMISSIONS:
        roles = held & review_steps._stage_roles(status)
        mine_at[status] = {key for key, chosen in by_step.items() if chosen & roles}

    pending = list(
        services.with_waiting_since(
            forms.filter(status__in=[status for status, steps in mine_at.items() if steps])
        ).values("id", "status", "revision", "waiting_since")
    )
    done = {}
    for row in ApplicationStepApproval.objects.filter(
        application_id__in=[form["id"] for form in pending]
    ).values("application_id", "revision", "step"):
        done.setdefault((row["application_id"], row["revision"]), set()).add(row["step"])

    waiting = [
        form
        for form in pending
        if mine_at[form["status"]] - done.get((form["id"], form["revision"]), set())
    ]
    now = timezone.now()
    since = [form["waiting_since"] for form in waiting if form["waiting_since"]]
    oldest = min(since, default=None)
    days = review_settings.overdue_days()
    late = now - timedelta(days=days)
    approved = ApplicationStepApproval.objects.filter(decided_by=membership.user)
    today = timezone.localdate()
    return {
        "waiting": len(waiting),
        "overdue": sum(1 for moment in since if moment < late),
        "overdue_days": days,
        "oldest_days": (now - oldest).days if oldest else None,
        "steps_today": approved.filter(decided_at__date=today).count(),
        "steps_week": approved.filter(decided_at__date__gte=today - timedelta(days=6)).count(),
    }


def _by_mcc(forms) -> list[dict]:
    late = timezone.now() - timedelta(days=review_settings.overdue_days())
    rows = (
        services.with_waiting_since(forms.filter(status__in=list(services.STAGES)))
        .values("mpp__mcc__code", "mpp__mcc__name")
        .annotate(waiting=Count("id"), overdue=Count("id", filter=Q(waiting_since__lt=late)))
        .order_by("-overdue", "-waiting")[:8]
    )
    return [
        {
            "code": row["mpp__mcc__code"],
            "name": row["mpp__mcc__name"],
            "waiting": row["waiting"],
            "overdue": row["overdue"],
        }
        for row in rows
    ]


def _trend(forms) -> list[dict]:
    start = timezone.localdate() - timedelta(days=TREND_DAYS - 1)
    submitted = dict(
        forms.filter(submitted_at__date__gte=start)
        .annotate(day=TruncDate("submitted_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    joined = dict(
        Member.objects.filter(application__in=forms, joined_at__date__gte=start)
        .annotate(day=TruncDate("joined_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    days = [start + timedelta(days=offset) for offset in range(TREND_DAYS)]
    return [
        {"day": day.isoformat(), "submitted": submitted.get(day, 0), "joined": joined.get(day, 0)}
        for day in days
    ]


def _fee(forms) -> dict:
    month = timezone.localdate().replace(day=1)
    at_fee = forms.filter(status__in=list(services.STAGES))
    collected = (
        Application.objects.filter(pk__in=forms.values("pk"), member__joined_at__date__gte=month)
        .exclude(payment={})
        .aggregate(total=Sum(Cast(KT("payment__amount"), IntegerField())))["total"]
    )
    return {
        "payment_missing": at_fee.filter(status=Status.PENDING_FINANCE, payment={}).count(),
        "collected_month": collected or 0,
    }


def _members(membership, permissions, forms) -> dict:
    month = timezone.localdate().replace(day=1)
    joined = Member.objects.filter(application__in=forms)
    existing = LegacyMember.objects.all()
    if (
        "mpp.view_all" not in permissions
        or MccAssignment.objects.filter(membership=membership, ended_at__isnull=True).exists()
    ):
        existing = existing.filter(mpp__in=forms.values("mpp"))
    return {
        "joined_month": joined.filter(joined_at__date__gte=month).count(),
        "joined_total": joined.count(),
        "existing_active": existing.filter(is_active=True).count(),
    }


def _setup() -> dict:
    """What still stops forms moving, for whoever runs the organization."""
    # Only those whose own signature is printed: facilitators, Area Managers and heads.
    approvers = Membership.objects.filter(
        Q(role_links__role__permissions__overlap=sorted(OWN_SIGNATURE_PERMISSIONS))
        | Q(pk__in=Signatory.objects.values("membership")),
        is_active=True,
    ).distinct()
    held = MccAssignment.objects.filter(
        ended_at__isnull=True,
        membership__role_links__role__permissions__contains=["applications.approve_am"],
    ).values("mcc")
    unassigned = [key for key, roles in review_steps.roles_by_step().items() if not roles]
    return {
        "steps_without_role": len(unassigned)
        if ReviewStepAccess.objects.exists()
        else len(review_steps.STEP_KEYS),
        "mccs_without_area_manager": Mcc.objects.filter(is_active=True)
        .exclude(pk__in=held)
        .count(),
        "signatures_missing": sum(1 for person in approvers if current_signature(person) is None),
        "signatories_missing": len(services.HEAD_SIGNED)
        - Signatory.objects.filter(stage__in=list(services.HEAD_SIGNED)).count(),
    }


def home_for(user) -> dict:
    membership = user.active_membership
    permissions = user.active_permissions
    can = permissions.__contains__
    forms = services.visible_applications(membership, permissions)

    home = {"by_status": services.status_counts(membership, permissions)}
    approves = bool(APPROVAL_PERMISSIONS & set(permissions))
    if approves:
        home["my_queue"] = _my_queue(membership, forms)
    if approves or can("reports.view"):
        home["by_mcc"] = _by_mcc(forms)
    if approves or can("reports.view") or can("settings.manage"):
        home["trend"] = _trend(forms)
    if review_steps.FEE_STEP in review_steps.my_steps(membership):
        home["fee"] = _fee(forms)
    if can("members.view"):
        home["members"] = _members(membership, permissions, forms)
    if can("settings.manage"):
        home["setup"] = _setup()
    if can("applications.create"):
        month = timezone.localdate().replace(day=1)
        home["mine"] = {
            "approved_month": Member.objects.filter(
                application__in=forms, joined_at__date__gte=month
            ).count(),
            "edited_by_me": forms.filter(
                Q(created_by=user) | Q(last_edited_by=user), status=Status.DRAFT
            ).count(),
        }
    return home


# What a breakdown row is grouped by: the id, the name shown, and a code when there is one.
GROUPS = {
    "facilitator": ("created_by", "created_by_name", None),
    "mcc": ("mpp__mcc", "mpp__mcc__name", "mpp__mcc__code"),
    "bmc": ("mpp__route__bmc", "mpp__route__bmc__name", "mpp__route__bmc__code"),
    "route": ("mpp__route", "mpp__route__name", "mpp__route__code"),
    "mpp": ("mpp", "mpp__name", "mpp__code"),
    # Each facilitator within each MCC, so an Area Manager reads it MCC by MCC.
    "mcc_facilitator": ("created_by", "created_by_name", None),
}
PARENTS = {"mcc_facilitator": ("mpp__mcc", "mpp__mcc__code", "mpp__mcc__name")}
COUNTS = ("started", "submitted", "pending", "approved", "rejected")


def _measures(forms, start, end) -> dict:
    """Each count's forms, between two dates. Pending: submitted then, still waiting now."""
    days = (start, end)
    submitted = forms.filter(submitted_at__date__range=days)
    return {
        "started": forms.filter(created_at__date__range=days),
        "submitted": submitted,
        "pending": submitted.filter(status__in=list(services.STAGES)),
        "approved": forms.filter(member__joined_at__date__range=days),
        "rejected": forms.filter(
            decisions__decision="rejected", decisions__decided_at__date__range=days
        ),
    }


def totals(forms, start, end) -> dict:
    return {
        count: queryset.order_by().values("id").distinct().count()
        for count, queryset in _measures(forms, start, end).items()
    }


def breakdown(user, by: str, start, end) -> list[dict]:
    """Who or where the work came from, between two dates."""
    forms = services.visible_applications(user.active_membership, user.active_permissions)
    key, name, code = GROUPS[by]
    parent = PARENTS.get(by)
    fields = [key, name, *([code] if code else []), *(parent or ())]
    rows: dict = {}

    for count, queryset in _measures(forms, start, end).items():
        grouped = queryset.order_by().values(*fields).annotate(total=Count("id", distinct=True))
        for row in grouped:
            identity = (row[parent[0]], row[key]) if parent else row[key]
            entry = rows.setdefault(
                identity,
                {
                    "key": "-".join(str(part) for part in identity)
                    if parent
                    else str(row[key] or ""),
                    "name": row[name] or "Not set",
                    "code": row.get(code) or "",
                    **(
                        {"group_code": row[parent[1]] or "", "group_name": row[parent[2]] or ""}
                        if parent
                        else {}
                    ),
                    **dict.fromkeys(COUNTS, 0),
                },
            )
            entry[count] = row["total"]

    order = (lambda row: (row["group_code"], -row["started"], row["name"])) if parent else None
    return sorted(
        rows.values(),
        key=order or (lambda row: (-row["started"], -row["submitted"], row["name"])),
    )
