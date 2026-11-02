import zipfile

from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.models import Application, GeneratedPdf
from apps.applications.services import display_name
from apps.audit.services import record_event
from apps.core.exceptions import Conflict, ErrorResponseSerializer, Gone
from apps.documents import storage
from apps.hierarchy.models import Bmc, Mcc, Mpp, Route
from apps.rbac.permissions import require_permission

from .models import BatchStatus, PdfBatch
from .serializers import (
    PdfBatchSerializer,
    PdfJobRequestSerializer,
    PrintFilterSerializer,
    PrintPreviewSerializer,
    ReportFilterSerializer,
    ReportSummarySerializer,
)
from .services import approved_for_print, export_workbook, filtered_applications, status_summary
from .tasks import KEEP_FOR, start_next

FULL_PDF = "applications.download_full_pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _clean_filters(data) -> dict:
    serializer = ReportFilterSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _applications(request, filters):
    user = request.user
    return filtered_applications(user.active_membership, user.active_permissions, filters)


class ReportSummaryView(APIView):
    permission_classes = [IsAuthenticated, require_permission("reports.view")]

    @extend_schema(parameters=[ReportFilterSerializer], responses={200: ReportSummarySerializer})
    def get(self, request):
        queryset = _applications(request, _clean_filters(request.query_params))
        counts = status_summary(queryset)
        return Response({"total": sum(counts.values()), "by_status": counts})


class ReportExportView(APIView):
    permission_classes = [IsAuthenticated, require_permission("reports.export")]

    @extend_schema(
        parameters=[ReportFilterSerializer], responses={(200, XLSX): OpenApiTypes.BINARY}
    )
    def get(self, request):
        filters = _clean_filters(request.query_params)
        content = export_workbook(_applications(request, filters))
        record_event(
            "report.exported",
            actor=request.user,
            metadata={key: str(value) for key, value in filters.items()},
        )
        response = HttpResponse(content, content_type=XLSX)
        stamp = timezone.localdate().isoformat()
        response["Content-Disposition"] = f'attachment; filename="applications-{stamp}.xlsx"'
        response["Cache-Control"] = "private, no-store"
        return response


MAX_FORMS_PER_JOB = 2000
PREVIEW_ROWS = 100
# Rough costs for the estimate shown before starting: seconds and bytes per form.
SECONDS_NEW = {"full": 1.6, "single": 0.6}
SECONDS_READY = 0.05
BYTES_PER_FORM = {"full": 1_200_000, "single": 250_000}


def _can_print(request, variant: str) -> None:
    held = request.user.active_permissions
    needed = FULL_PDF if variant == "full" else "applications.view"
    if needed not in held:
        raise exceptions.PermissionDenied("You cannot print this kind of form.")


def _to_print(request, filters):
    user = request.user
    return approved_for_print(user.active_membership, user.active_permissions, filters)


def _label(filters: dict) -> str:
    parts = []
    start, end = filters.get("approved_from"), filters.get("approved_to")
    if start or end:
        shown = [value.strftime("%d-%m-%Y") if value else "…" for value in (start, end)]
        parts.append(f"Approved {shown[0]} to {shown[1]}")
    for key, model in (("mcc", Mcc), ("bmc", Bmc), ("route", Route), ("mpp", Mpp)):
        if filters.get(key):
            place = model.objects.filter(pk=filters[key]).first()
            if place:
                parts.append(f"{key.upper()} {place.code} {place.name}")
    if filters.get("search"):
        parts.append(f"Search “{filters['search']}”")
    return " · ".join(parts) or "All approved members"


class PdfPreviewView(APIView):
    """How many forms a filter picks, and how long they will take, before anything starts."""

    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(request=PdfJobRequestSerializer, responses={200: PrintPreviewSerializer})
    def post(self, request):
        serializer = PrintFilterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        variant = request.data.get("variant", "full")
        variant = variant if variant in SECONDS_NEW else "full"
        forms = _to_print(request, serializer.validated_data)
        count = forms.count()
        ready = (
            GeneratedPdf.objects.filter(application__in=forms, variant=variant).count()
            if count <= MAX_FORMS_PER_JOB
            else 0
        )
        rows = [
            {
                "id": application.id,
                "form_number": application.form_number,
                "full_name": application.member.full_name,
                "tr_code": application.member.tr_code,
                "mpp": f"{application.mpp.code} {application.mpp.name}",
                "approved_at": application.member.joined_at,
            }
            for application in forms[:PREVIEW_ROWS]
        ]
        return Response(
            {
                "count": count,
                "limit": MAX_FORMS_PER_JOB,
                "ready": ready,
                "estimated_seconds": round(
                    (count - ready) * SECONDS_NEW[variant] + ready * SECONDS_READY
                ),
                "estimated_bytes": count * BYTES_PER_FORM[variant],
                "rows": rows,
            }
        )


class PdfBatchListView(generics.ListAPIView):
    """A person's own PDF jobs, newest first."""

    serializer_class = PdfBatchSerializer
    permission_classes = [IsAuthenticated, require_permission("applications.view")]
    filterset_fields = ["status"]
    ordering_fields = ["created_at", "status", "form_count"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PdfBatch.objects.none()
        return PdfBatch.objects.filter(requested_by=self.request.user).order_by("-created_at")

    @extend_schema(
        request=PdfJobRequestSerializer,
        responses={202: PdfBatchSerializer, 400: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = PdfJobRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _can_print(request, data["variant"])

        user = request.user
        if PdfBatch.objects.filter(
            requested_by=user, status__in=[BatchStatus.QUEUED, BatchStatus.RUNNING]
        ).exists():
            raise Conflict("Your earlier PDF job is still going. Wait for it, or cancel it.")

        excluded = {str(pk) for pk in data.get("exclude", [])}
        ids = [
            str(pk)
            for pk in _to_print(request, data).values_list("id", flat=True)[
                : MAX_FORMS_PER_JOB + len(excluded) + 1
            ]
            if str(pk) not in excluded
        ]
        if not ids:
            raise exceptions.ValidationError({"detail": ["No approved members match this filter."]})
        if len(ids) > MAX_FORMS_PER_JOB:
            raise exceptions.ValidationError(
                {"detail": [f"Choose at most {MAX_FORMS_PER_JOB} forms. Narrow the dates."]}
            )

        organization_id = user.active_membership.organization_id
        batch = PdfBatch.objects.create(
            organization_id=organization_id,
            variant=data["variant"],
            want_zip=data["want_zip"],
            want_merged=data["want_merged"],
            label=_label(data)[:300],
            filters={"application_ids": ids},
            form_count=len(ids),
            requested_by=user,
            requested_by_name=display_name(user),
        )
        record_event(
            "report.pdf_batch_requested",
            actor=user,
            target=batch,
            metadata={"forms": len(ids), "variant": batch.variant},
        )
        start_next(organization_id)
        batch.refresh_from_db()
        return Response(PdfBatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)


def _own_batch(request, pk) -> PdfBatch:
    return get_object_or_404(PdfBatch, pk=pk, requested_by=request.user)


class PdfBatchDetailView(APIView):
    """Polled while a job runs, for its progress."""

    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(responses={200: PdfBatchSerializer})
    def get(self, request, pk):
        response = Response(PdfBatchSerializer(_own_batch(request, pk)).data)
        response["Cache-Control"] = "no-store"
        return response


class PdfBatchCancelView(APIView):
    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(request=None, responses={200: PdfBatchSerializer, 409: ErrorResponseSerializer})
    def post(self, request, pk):
        batch = PdfBatch.objects.select_for_update().filter(pk=_own_batch(request, pk).pk).get()
        if batch.status not in (BatchStatus.QUEUED, BatchStatus.RUNNING):
            raise Conflict("This job has already ended.")
        batch.status = BatchStatus.CANCELLED
        batch.finished_at = timezone.now()
        batch.save(update_fields=["status", "finished_at", "updated_at"])
        record_event("report.pdf_batch_cancelled", actor=request.user, target=batch)
        return Response(PdfBatchSerializer(batch).data)


class PdfBatchRetryView(APIView):
    """A new job for just the forms that could not be made."""

    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(request=None, responses={202: PdfBatchSerializer, 400: ErrorResponseSerializer})
    def post(self, request, pk):
        old = _own_batch(request, pk)
        _can_print(request, old.variant)
        failed = set(old.failed_forms)
        ids = [
            str(pk)
            for pk, number in Application.objects.filter(pk__in=old.application_ids).values_list(
                "id", "form_number"
            )
            if number in failed or str(pk) in failed
        ]
        if not ids:
            raise exceptions.ValidationError({"detail": ["Nothing failed in this job."]})
        batch = PdfBatch.objects.create(
            organization_id=old.organization_id,
            variant=old.variant,
            want_zip=old.want_zip,
            want_merged=old.want_merged,
            label=f"Retry: {old.label}"[:300],
            filters={"application_ids": ids},
            form_count=len(ids),
            requested_by=request.user,
            requested_by_name=display_name(request.user),
        )
        start_next(old.organization_id)
        batch.refresh_from_db()
        return Response(PdfBatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)


def _downloadable(request, pk) -> PdfBatch:
    batch = _own_batch(request, pk)
    _can_print(request, batch.variant)
    if batch.status != BatchStatus.DONE:
        raise Conflict("This job is not finished.")
    if batch.finished_at and timezone.now() > batch.finished_at + KEEP_FOR:
        raise Gone("These files were removed after 7 days. Start the job again.")
    return batch


class _Sink:
    """Collects what zipfile writes, handed on piece by piece to the response."""

    def __init__(self):
        self.pieces = []

    def write(self, data) -> int:
        self.pieces.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def take(self) -> bytes:
        data, self.pieces = b"".join(self.pieces), []
        return data


def _zip_stream(files):
    """One form at a time: a ZIP of 2000 forms never sits whole in memory."""
    sink = _Sink()
    # Stored, not compressed: PDFs are compressed already.
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name, path in files:
            with archive.open(name, "w", force_zip64=True) as entry:
                entry.write(storage.read(path))
            yield sink.take()
    yield sink.take()


class PdfBatchZipView(APIView):
    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        batch = _downloadable(request, pk)
        if not batch.want_zip:
            raise exceptions.NotFound("This job made print files only.")
        # Read now, inside this request's organization. The stream itself only reads files.
        stored = dict(
            GeneratedPdf.objects.filter(
                application_id__in=batch.application_ids, variant=batch.variant
            ).values_list("application_id", "relative_path")
        )
        files = [
            (f"{number}.pdf", stored[pk])
            for pk, number in Application.objects.filter(pk__in=batch.application_ids)
            .order_by("form_number")
            .values_list("id", "form_number")
            if pk in stored
        ]
        record_event(
            "report.pdf_batch_downloaded",
            actor=request.user,
            target=batch,
            metadata={"format": "zip", "forms": len(files)},
        )
        response = StreamingHttpResponse(_zip_stream(files), content_type="application/zip")
        stamp = timezone.localtime(batch.created_at).strftime("%Y%m%d-%H%M")
        response["Content-Disposition"] = (
            f'attachment; filename="forms-{batch.variant}-{stamp}.zip"'
        )
        response["Cache-Control"] = "private, no-store"
        return response


class PdfBatchFileView(APIView):
    """One merged print file of the job."""

    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(
        parameters=[OpenApiParameter("part", int, required=False)],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        batch = _downloadable(request, pk)
        try:
            index = int(request.query_params.get("part", 0))
            part = batch.merged_parts[index]
        except ValueError, IndexError:
            raise exceptions.NotFound("No such print file.") from None
        record_event(
            "report.pdf_batch_downloaded",
            actor=request.user,
            target=batch,
            metadata={"format": "merged", "part": index},
        )
        response = HttpResponse(storage.read(part["path"]), content_type="application/pdf")
        name = part.get("name") or f"part-{index + 1}"
        response["Content-Disposition"] = f'attachment; filename="forms-{name}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
