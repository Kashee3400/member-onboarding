from io import BytesIO

from django.db.models import Count, Q
from django.utils import timezone
from openpyxl import Workbook

from apps.applications.models import Application, Status
from apps.hierarchy.services import accessible_mpps

EXPORT_COLUMNS = (
    "Form number",
    "Member code",
    "Applicant",
    "Mobile",
    "MPP code",
    "MPP name",
    "MCC code",
    "Status",
    "Prepared by",
    "Submitted on",
    "Approved on",
)


def filtered_applications(membership, permissions, filters: dict):
    """Reports follow the same MPP access as the screens, so exports cannot show more."""
    queryset = (
        Application.objects.filter(mpp__in=accessible_mpps(membership, permissions))
        .exclude(status=Status.DISCARDED)
        .select_related("mpp__mcc", "member")
    )
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    if filters.get("mpp"):
        queryset = queryset.filter(mpp_id=filters["mpp"])
    if filters.get("mcc"):
        queryset = queryset.filter(mpp__mcc_id=filters["mcc"])
    if filters.get("submitted_from"):
        queryset = queryset.filter(submitted_at__date__gte=filters["submitted_from"])
    if filters.get("submitted_to"):
        queryset = queryset.filter(submitted_at__date__lte=filters["submitted_to"])
    return queryset


def approved_for_print(membership, permissions, filters: dict):
    """Members made through this portal, by the day of final approval, oldest form first."""
    queryset = (
        Application.objects.filter(
            mpp__in=accessible_mpps(membership, permissions),
            status=Status.APPROVED,
            member__isnull=False,
        )
        .select_related("mpp", "member")
        .order_by("form_number")
    )
    if filters.get("approved_from"):
        queryset = queryset.filter(member__joined_at__date__gte=filters["approved_from"])
    if filters.get("approved_to"):
        queryset = queryset.filter(member__joined_at__date__lte=filters["approved_to"])
    for key, field in (
        ("mpp", "mpp_id"),
        ("route", "mpp__route_id"),
        ("bmc", "mpp__route__bmc_id"),
        ("mcc", "mpp__mcc_id"),
    ):
        if filters.get(key):
            queryset = queryset.filter(**{field: filters[key]})
    if text := (filters.get("search") or "").strip():
        queryset = queryset.filter(
            Q(form_number__iexact=text)
            | Q(member__tr_code=text)
            | Q(member__mobile=text)
            | Q(member__full_name__icontains=text)
        )
    return queryset


def status_summary(queryset) -> dict:
    counts = queryset.order_by().values("status").annotate(total=Count("id"))
    return {row["status"]: row["total"] for row in counts}


def _safe_cell(value):
    """A value starting like a formula would run in Excel, so it is forced to plain text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def _local_date(moment):
    return timezone.localtime(moment).strftime("%d-%m-%Y") if moment else ""


def export_workbook(queryset) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Applications")
    sheet.append(EXPORT_COLUMNS)

    for application in queryset.order_by("submitted_at", "created_at").iterator(chunk_size=500):
        member = getattr(application, "member", None)
        data = application.data
        sheet.append(
            [
                _safe_cell(value)
                for value in (
                    application.form_number,
                    member.tr_code if member else "",
                    data.get("applicant", {}).get("full_name", ""),
                    data.get("address", {}).get("mobile", ""),
                    application.mpp.code,
                    application.mpp.name,
                    application.mpp.mcc.code,
                    application.get_status_display(),
                    application.created_by_name,
                    _local_date(application.submitted_at),
                    _local_date(member.joined_at) if member else "",
                )
            ]
        )

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
