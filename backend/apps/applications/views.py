from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as filters
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import Conflict, ErrorResponseSerializer
from apps.documents import storage
from apps.documents.models import Document
from apps.documents.services import current_signature
from apps.hierarchy.models import Mpp
from apps.hierarchy.services import accessible_mpps
from apps.organizations.models import Membership
from apps.rbac.catalog import APPROVE_ALL
from apps.rbac.models import Role
from apps.rbac.permissions import require_permission

from . import (
    banks,
    form,
    form_lists,
    home,
    place,
    review_checks,
    review_settings,
    review_steps,
    services,
)
from . import marks as field_marks
from .data_export import member_data_archive
from .models import (
    Application,
    BankBranch,
    LegacyMember,
    Member,
    ReviewStepAccess,
    Signatory,
    Status,
)
from .pdf.render import VARIANTS
from .serializers import (
    ApplicationCreateSerializer,
    ApplicationDetailSerializer,
    ApplicationListSerializer,
    ApplicationSaveSerializer,
    BankBranchLookupSerializer,
    BankBranchSerializer,
    BankImportResultSerializer,
    BankImportSerializer,
    DecideSerializer,
    FieldMarkSerializer,
    FormListSerializer,
    LegacyMemberSerializer,
    MemberCodeSettingsSerializer,
    MemberSerializer,
    OrganizationProfileSerializer,
    PaymentSerializer,
    RejectReasonSerializer,
    ReviewSettingsSerializer,
    ReviewStepAccessSerializer,
    SearchHitSerializer,
    SensitiveNumbersSerializer,
    StatusCountsSerializer,
    StepTickSerializer,
    StepTicksSerializer,
    SubmitSerializer,
)

FULL_PDF = "applications.download_full_pdf"
SEARCH_LIMIT = 5
MIN_SEARCH_LENGTH = 2


# Those who must check a form's numbers against its card and passbook photos.
NUMBER_VIEWERS = {
    APPROVE_ALL,
    "applications.approve_am",
    "applications.approve_cs",
    "applications.approve_finance",
}


class FormSchemaView(APIView):
    """The form definition, so clients render exactly what the server validates."""

    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        schema = form_lists.schema()
        # What the member pays, so the app can say so before she signs.
        settings = services.code_settings()
        schema["fee"] = {
            "admission_fee": settings.entry_fee,
            "share_count": settings.share_count,
            "share_price": settings.share_price,
            "total": settings.entry_fee + settings.share_count * settings.share_price,
        }
        return Response(schema)


class StatusIn(filters.BaseInFilter, filters.CharFilter):
    pass


class ApplicationFilter(filters.FilterSet):
    status = StatusIn(field_name="status", lookup_expr="in")
    created_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    approved_from = filters.DateFilter(field_name="member__joined_at", lookup_expr="date__gte")
    approved_to = filters.DateFilter(field_name="member__joined_at", lookup_expr="date__lte")
    mine = filters.BooleanFilter(method="filter_mine", help_text="Only forms this person started.")

    def filter_mine(self, queryset, name, value):
        return queryset.filter(created_by=self.request.user) if value else queryset

    class Meta:
        model = Application
        fields = ["mpp"]


class ApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = ApplicationFilter
    search_fields = ["form_number", "search_name", "mpp__code", "mpp__name", "member__tr_code"]
    ordering_fields = [
        "form_number",
        "submitted_at",
        "waiting_since",
        "updated_at",
        "status",
        "member__joined_at",
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Application.objects.none()
        user = self.request.user
        forms = services.searchable_applications(
            user.active_membership, user.active_permissions
        ).select_related("mpp", "member")
        if self.action not in ("list", "retrieve"):
            return forms
        # The member's photo, so a list can show who each form is for.
        photo = Document.objects.filter(
            application=OuterRef("pk"), document_type="photo", is_current=True
        ).values("id")[:1]
        return services.with_waiting_since(forms).annotate(photo_id=Subquery(photo))

    def get_serializer_class(self):
        return ApplicationListSerializer if self.action == "list" else ApplicationDetailSerializer

    def get_permissions(self):
        required = {
            "create": "applications.create",
            "partial_update": "applications.edit",
            "discard": "applications.edit",
            "submit": "applications.submit",
            "data_export": "members.export_data",
        }.get(self.action, "applications.view")
        if self.action in (
            "decide",
            "payment",
            "numbers",
            "checks",
            "marks",
            "unmark",
            "withdraw_step",
        ):
            # Which approval permission applies depends on the stage.
            return [IsAuthenticated()]
        return [IsAuthenticated(), require_permission(required)()]

    def _locked(self):
        application = self.get_object()
        return (
            Application.objects.select_for_update(of=("self",))
            .select_related("mpp")
            .get(pk=application.pk)
        )

    def _detail(self, application, status_code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=application.pk)
        # Not stored: what this save refused, which only the object that saved knows.
        fresh.duplicate_fields = getattr(application, "duplicate_fields", {})
        context = self.get_serializer_context()
        return Response(
            ApplicationDetailSerializer(fresh, context=context).data, status=status_code
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE),
            OpenApiParameter("to", OpenApiTypes.DATE),
            OpenApiParameter("mine", OpenApiTypes.BOOL),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], filterset_class=None, pagination_class=None)
    def summary(self, request):
        """How many forms were started, submitted, approved and so on, between two dates."""
        forms = self.get_queryset()
        if request.query_params.get("mine") in ("1", "true"):
            forms = forms.filter(created_by=request.user)
        start, end = _date_range(request)
        # Events in the period (older apps read these) and where its forms stand now.
        return Response(
            {
                "from": start,
                "to": end,
                **home.totals(forms, start, end),
                "now": home.status_totals(forms, start, end),
            }
        )

    @extend_schema(responses={200: StatusCountsSerializer})
    @action(detail=False, methods=["get"], filterset_class=None, pagination_class=None)
    def counts(self, request):
        user = request.user
        by_status = services.status_counts(user.active_membership, user.active_permissions)
        return Response({"by_status": by_status, "total": sum(by_status.values())})

    @extend_schema(
        request=ApplicationCreateSerializer,
        responses={201: ApplicationDetailSerializer, 200: ApplicationDetailSerializer},
    )
    def create(self, request):
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        allowed = accessible_mpps(user.active_membership, user.active_permissions)
        if not allowed.filter(pk=data["mpp"].pk).exists():
            raise exceptions.PermissionDenied("This MPP is not assigned to you.")

        # A retry from a device on a poor network returns the same draft.
        existing = Application.objects.filter(client_id=data["client_id"]).first()
        if existing:
            return self._detail(existing)

        name = services.display_name(user)
        try:
            with transaction.atomic():
                application = Application(
                    organization_id=user.active_membership.organization_id,
                    client_id=data["client_id"],
                    mpp=data["mpp"],
                    form_version=form.FORM_VERSION,
                    created_by=user,
                    created_by_name=name,
                    last_edited_by=user,
                    last_edited_by_name=name,
                )
                place.apply(application)
                application.save()
        except IntegrityError as exc:
            raise Conflict("This draft was just created. Please retry.") from exc

        record_event("application.created", actor=user, target=application)
        return self._detail(application, status.HTTP_201_CREATED)

    @extend_schema(
        request=ApplicationSaveSerializer,
        responses={
            200: ApplicationDetailSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    def partial_update(self, request, pk=None):
        serializer = ApplicationSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        application = services.save_draft(
            self._locked(),
            user=request.user,
            data=data.get("data"),
            aadhaar=data.get("aadhaar_number"),
            account=data.get("account_number"),
            version=data.get("version"),
            aadhaar_qr=data.get("aadhaar_qr"),
            aadhaar_qr_consent=data.get("aadhaar_qr_consent", False),
        )
        return self._detail(application)

    @extend_schema(
        request=SubmitSerializer,
        responses={
            200: ApplicationDetailSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        serializer = SubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = services.submit(
            self._locked(), user=request.user, version=serializer.validated_data.get("version")
        )
        return self._detail(application)

    @extend_schema(
        request=None, responses={204: None, 409: ErrorResponseSerializer}, methods=["POST"]
    )
    @action(detail=True, methods=["post"])
    def discard(self, request, pk=None):
        application = self._locked()
        if application.status != Status.DRAFT or application.revision:
            raise Conflict("Only a draft that was never submitted can be discarded.")
        application.status = Status.DISCARDED
        application.save(update_fields=["status", "updated_at"])
        record_event("application.discarded", actor=request.user, target=application)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=DecideSerializer,
        responses={
            200: ApplicationDetailSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        serializer = DecideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        application = services.decide(
            self.get_object(),
            user=request.user,
            permissions=request.user.active_permissions,
            decision=data["decision"],
            reason=data.get("reason", ""),
            rejected_fields=data.get("rejected_fields"),
            steps=data.get("steps"),
            field_notes=data.get("field_notes"),
        )
        return self._detail(application)

    def _marks(self, application):
        return Response(
            FieldMarkSerializer(
                field_marks.serialized(application, self.request.user), many=True
            ).data
        )

    @extend_schema(
        methods=["GET"],
        request=None,
        responses={200: FieldMarkSerializer(many=True), 403: ErrorResponseSerializer},
    )
    @extend_schema(
        methods=["PUT"],
        request=FieldMarkSerializer,
        responses={
            200: FieldMarkSerializer(many=True),
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["get", "put"])
    def marks(self, request, pk=None):
        """
        Fields marked wrong on this submission, by everyone reviewing it. A PUT marks one
        field, or changes the reason of this person's mark on it.
        """
        if not NUMBER_VIEWERS & set(request.user.active_permissions):
            raise exceptions.PermissionDenied("Only reviewers see marked fields.")
        application = self.get_object()
        if request.method == "PUT":
            serializer = FieldMarkSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            field_marks.mark(application, user=request.user, **serializer.validated_data)
        return self._marks(application)

    @extend_schema(
        request=None,
        responses={
            200: FieldMarkSerializer(many=True),
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["delete"], url_path=r"marks/(?P<mark_id>[0-9a-f-]{36})")
    def unmark(self, request, pk=None, mark_id=None):
        application = self.get_object()
        field_marks.unmark(application, user=request.user, mark_id=mark_id)
        return self._marks(application)

    @extend_schema(
        request=None,
        responses={
            200: ApplicationDetailSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path=r"steps/(?P<step>[a-z_]+)/withdraw")
    def withdraw_step(self, request, pk=None, step=None):
        """Takes back a step approval given by mistake, while the form is at that stage."""
        application = services.withdraw_step(self.get_object(), user=request.user, step=step)
        return self._detail(application)

    @extend_schema(
        request=StepTickSerializer,
        responses={
            200: StepTicksSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"])
    def checks(self, request, pk=None):
        """Ticks or unticks one check of a step this person can approve now."""
        serializer = StepTickSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ticked = review_checks.tick(
            self.get_object(),
            user=request.user,
            step=data["step"],
            text=data["text"],
            on=data["ticked"],
        )
        return Response({"step": data["step"], "ticked": ticked})

    @extend_schema(
        request=None,
        responses={200: SensitiveNumbersSerializer, 403: ErrorResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def numbers(self, request, pk=None):
        """A POST, so nothing caches it. Every look is written to the audit log."""
        if not NUMBER_VIEWERS & set(request.user.active_permissions):
            raise exceptions.PermissionDenied("Only approvers can see the full numbers.")
        numbers = services.sensitive_numbers(self.get_object(), user=request.user)
        return Response(numbers, headers={"Cache-Control": "no-store"})

    @extend_schema(
        request=PaymentSerializer,
        responses={
            200: ApplicationDetailSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["post"])
    def payment(self, request, pk=None):
        serializer = PaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = services.record_payment(
            self._locked(),
            user=request.user,
            permissions=request.user.active_permissions,
            payment=serializer.validated_data,
        )
        return self._detail(application)

    @extend_schema(
        parameters=[
            OpenApiParameter("variant", str, enum=["full", "single"], description="Default: full.")
        ],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY, 409: ErrorResponseSerializer},
    )
    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        variant = _pdf_variant(request)
        application = self.get_object()
        content = services.printed_form(application, variant)
        record_event(
            "application.pdf_downloaded",
            actor=request.user,
            target=application,
            metadata={"variant": variant},
        )
        return _pdf_response(content, f"{application.form_number}.pdf")

    @extend_schema(
        parameters=[
            OpenApiParameter("variant", str, enum=["full", "single"], description="Default: full.")
        ],
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            403: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @action(detail=True, methods=["get"], url_path="preview-pdf")
    def preview_pdf(self, request, pk=None):
        """The printed form before final approval, marked as a draft. Nothing is stored."""
        variant = _pdf_variant(request)
        if not NUMBER_VIEWERS & set(request.user.active_permissions):
            raise exceptions.PermissionDenied("Only approvers can preview the form.")

        application = self.get_object()
        content = services.draft_form(application, variant)
        record_event(
            "application.pdf_previewed",
            actor=request.user,
            target=application,
            metadata={"variant": variant, "status": application.status},
        )
        return _pdf_response(content, f"{application.form_number}-draft.pdf")

    @extend_schema(
        responses={(200, "image/jpeg"): OpenApiTypes.BINARY, 404: ErrorResponseSerializer}
    )
    @action(detail=True, methods=["get"], url_path="aadhaar-photo")
    def aadhaar_photo(self, request, pk=None):
        """The member's photo from her Aadhaar QR, to compare with the profile photo."""
        application = self.get_object()
        check = getattr(application, "aadhaar_check", None)
        if check is None or not check.photo_path:
            raise exceptions.NotFound("No photo was read from the Aadhaar QR.")
        record_event("application.aadhaar_photo_viewed", actor=request.user, target=application)
        response = HttpResponse(storage.read(check.photo_path), content_type="image/jpeg")
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="data-export")
    def data_export(self, request, pk=None):
        """Everything held about this form's member, decrypted. Always audited."""
        application = self.get_object()
        content = member_data_archive(application, user=request.user)
        name = application.form_number or str(application.pk)
        return _zip_response(content, f"member-data-{name}.zip")


def _zip_response(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


def _pdf_variant(request) -> str:
    variant = request.query_params.get("variant", "full")
    if variant not in VARIANTS:
        raise exceptions.ValidationError({"variant": ["Choose full or single."]})
    # Only the full form carries Aadhaar and bank images.
    if variant == "full" and FULL_PDF not in request.user.active_permissions:
        raise exceptions.PermissionDenied("You cannot download the full form.")
    return variant


def _pdf_response(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


class MemberViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, require_permission("members.view")]
    filterset_fields = ["mpp"]
    search_fields = ["tr_code", "full_name", "mpp__code"]
    ordering_fields = ["tr_code", "full_name", "joined_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Member.objects.none()
        user = self.request.user
        allowed = accessible_mpps(user.active_membership, user.active_permissions)
        return Member.objects.filter(mpp__in=allowed).select_related("mpp")


class LegacyMemberViewSet(viewsets.ReadOnlyModelViewSet):
    """Members from before this system. Those whose MPP is gone stay with whoever sees all."""

    serializer_class = LegacyMemberSerializer
    permission_classes = [IsAuthenticated, require_permission("members.view")]
    filterset_fields = ["mpp", "is_active"]
    search_fields = ["tr_code", "full_name", "mpp__code", "mpp__name"]
    ordering_fields = ["tr_code", "full_name"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LegacyMember.objects.none()
        user = self.request.user
        queryset = LegacyMember.objects.select_related("mpp")
        if "mpp.view_all" in user.active_permissions:
            return queryset
        return queryset.filter(
            mpp__in=accessible_mpps(user.active_membership, user.active_permissions)
        )


class OrganizationProfileView(APIView):
    permission_classes = [IsAuthenticated, require_permission("settings.member_code")]

    @extend_schema(responses={200: OrganizationProfileSerializer})
    def get(self, request):
        return Response(OrganizationProfileSerializer(services.organization_profile()).data)

    @extend_schema(
        request=OrganizationProfileSerializer, responses={200: OrganizationProfileSerializer}
    )
    def put(self, request):
        profile = services.organization_profile()
        serializer = OrganizationProfileSerializer(profile, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_event("organization.profile_updated", actor=request.user, target=profile)
        return Response(serializer.data)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, require_permission("dashboard.view")]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        user = request.user
        by_status = services.status_counts(user.active_membership, user.active_permissions)
        waiting = sum(
            by_status.get(stage, 0)
            for stage, (permission, _) in services.STAGES.items()
            if permission in user.active_permissions
        )
        return Response({"by_status": by_status, "waiting_for_me": waiting})


class HomeView(APIView):
    """The numbers for the home page, chosen by what this person does."""

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(home.home_for(request.user))


class HomeBreakdownView(APIView):
    """Counts per facilitator, or per MCC, BMC, route or MPP, for a day or a range."""

    @extend_schema(
        parameters=[
            OpenApiParameter("by", str, enum=list(home.GROUPS)),
            OpenApiParameter("from", OpenApiTypes.DATE),
            OpenApiParameter("to", OpenApiTypes.DATE),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        permissions = request.user.active_permissions
        if not {"dashboard.view", "reports.view"} & set(permissions):
            raise exceptions.PermissionDenied("You cannot see these numbers.")

        by = request.query_params.get("by") or "facilitator"
        if by not in home.GROUPS:
            raise exceptions.ValidationError({"by": [f"Choose one of {', '.join(home.GROUPS)}."]})
        start, end = _date_range(request)
        return Response(home.breakdown(request.user, by, start, end))


def _date_range(request):
    """`from` and `to` as dates. Without them, today; with only `from`, up to today."""
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.query_params.get("from") or today.isoformat())
        end = date.fromisoformat(request.query_params.get("to") or today.isoformat())
    except ValueError as exc:
        raise exceptions.ValidationError({"from": ["Use dates like 2026-11-02."]}) from exc
    if end < start:
        raise exceptions.ValidationError({"to": ["The end date is before the start."]})
    return start, end


def _application_hits(membership, permissions, needle):
    found = (
        services.searchable_applications(membership, permissions)
        .filter(
            Q(form_number__icontains=needle)
            | Q(search_name__icontains=needle)
            | Q(mpp__code__icontains=needle)
            | Q(mpp__name__icontains=needle)
            | Q(member__tr_code__icontains=needle)
        )
        .select_related("mpp")
        .order_by("-updated_at")[:SEARCH_LIMIT]
    )
    return [
        {
            "kind": "application",
            "id": application.id,
            "title": application.search_name or application.form_number or "Draft",
            "subtitle": " · ".join(
                filter(
                    None,
                    [
                        application.form_number,
                        application.get_status_display(),
                        application.mpp.code,
                    ],
                )
            ),
            "path": f"/applications/{application.id}",
        }
        for application in found
    ]


def _member_hits(membership, permissions, needle):
    found = (
        Member.objects.filter(mpp__in=accessible_mpps(membership, permissions))
        .filter(
            Q(tr_code__icontains=needle)
            | Q(full_name__icontains=needle)
            | Q(mpp__code__icontains=needle)
        )
        .select_related("mpp")
        .order_by("full_name")[:SEARCH_LIMIT]
    )
    return [
        {
            "kind": "member",
            "id": member.id,
            "title": member.full_name,
            "subtitle": f"{member.tr_code} · {member.mpp.code}",
            "path": f"/members?q={member.tr_code}",
        }
        for member in found
    ]


class GlobalSearchView(APIView):
    """What Ctrl+K finds. Each kind appears only for those allowed to list it."""

    @extend_schema(
        parameters=[OpenApiParameter("q", str, required=True)],
        responses={200: SearchHitSerializer(many=True)},
    )
    def get(self, request):
        needle = request.query_params.get("q", "").strip()
        if len(needle) < MIN_SEARCH_LENGTH:
            return Response([])

        user = request.user
        membership, permissions = user.active_membership, user.active_permissions
        hits = []
        if "applications.view" in permissions:
            hits += _application_hits(membership, permissions, needle)
        if "members.view" in permissions:
            hits += _member_hits(membership, permissions, needle)
        return Response(SearchHitSerializer(hits, many=True).data)


class MppOpenWorkView(APIView):
    """What a handover would move. Drafts that never left a phone cannot appear here."""

    permission_classes = [IsAuthenticated, require_permission("mpp.assign")]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        mpp = get_object_or_404(Mpp, pk=pk)
        open_forms = Application.objects.filter(
            mpp=mpp, status__in=services.EDITABLE_STATUSES
        ).order_by("-updated_at")
        return Response(
            {
                "drafts": [
                    {
                        "id": str(application.id),
                        "status": application.status,
                        "applicant_name": application.data.get("applicant", {}).get(
                            "full_name", ""
                        ),
                        "last_edited_by_name": application.last_edited_by_name,
                        "updated_at": application.updated_at,
                    }
                    for application in open_forms
                ]
            }
        )


class ReviewStepAccessView(APIView):
    """Which role acts on which step of the form. Everyone can still read every step."""

    permission_classes = [IsAuthenticated, require_permission("settings.review_steps")]

    def _state(self):
        saved = review_steps.roles_by_step()
        return {
            "steps": [
                {
                    "key": step["key"],
                    "number": step["number"],
                    "title": step["title"],
                    "roles": sorted(saved[step["key"]]),
                }
                for step in review_steps.steps_for(None)
            ],
            "roles": [
                {"code": role.code, "name": role.name} for role in review_steps.approver_roles()
            ],
        }

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(self._state())

    @extend_schema(
        request=ReviewStepAccessSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: ErrorResponseSerializer},
    )
    def put(self, request):
        serializer = ReviewStepAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chosen = serializer.validated_data["steps"]

        roles = {role.code: role for role in review_steps.approver_roles()}
        if set(chosen) != set(review_steps.STEP_KEYS):
            raise exceptions.ValidationError({"steps": ["Send every step."]})
        for codes in chosen.values():
            if not codes:
                raise exceptions.ValidationError({"steps": ["Every step needs a role."]})
            if not set(codes) <= set(roles):
                raise exceptions.ValidationError({"steps": ["Choose only approver roles."]})

        ReviewStepAccess.objects.all().delete()
        ReviewStepAccess.objects.bulk_create(
            ReviewStepAccess(
                organization_id=request.user.active_membership.organization_id,
                step=key,
                role=roles[code],
            )
            for key, codes in chosen.items()
            for code in set(codes)
        )
        record_event("review_steps.updated", actor=request.user, metadata=chosen)
        return Response(self._state())


class RejectReasonsView(APIView):
    """The ready-made reasons a reviewer can pick when sending a form back."""

    permission_classes = [IsAuthenticated, require_permission("applications.view")]

    @extend_schema(responses={200: RejectReasonSerializer(many=True)})
    def get(self, request):
        return Response(review_settings.serialized(review_settings.reject_reasons()))


class ReviewSettingsView(APIView):
    """When a waiting form is late, the reject reasons reviewers are offered, and checklists."""

    permission_classes = [IsAuthenticated, require_permission("settings.review_steps")]

    def _state(self):
        return {
            "overdue_days": review_settings.overdue_days(),
            "reject_reasons": review_settings.serialized(review_settings.reject_reasons()),
            "sections": review_settings.sections(),
            "checks": review_checks.by_step(),
            "steps": [
                {"key": step.key, "number": number, "title": step.title}
                for number, step in enumerate(review_steps.STEPS, start=1)
            ],
        }

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(self._state())

    @extend_schema(
        request=ReviewSettingsSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: ErrorResponseSerializer},
    )
    def put(self, request):
        serializer = ReviewSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        metadata = {
            "overdue_days": data["overdue_days"],
            "reject_reasons": len(data["reject_reasons"]),
        }
        with transaction.atomic():
            review_settings.save(overdue_days=data["overdue_days"], reasons=data["reject_reasons"])
            if "checks" in data:
                review_checks.save(data["checks"])
                metadata["checks"] = {key: len(texts) for key, texts in data["checks"].items()}
        record_event("review_settings.updated", actor=request.user, metadata=metadata)
        return Response(self._state())


class SignatoriesView(APIView):
    """Who signs the printed form for each stage a team works."""

    permission_classes = [IsAuthenticated, require_permission("settings.review_steps")]

    def _state(self):
        chosen = {row.stage: row.membership_id for row in Signatory.objects.all()}
        stages = []
        for stage, label in services.HEAD_SIGNED.items():
            permission = services.STAGES[stage][0]
            roles = Role.objects.filter(permissions__contains=[permission])
            people = (
                Membership.objects.filter(is_active=True, role_links__role__in=roles)
                .select_related("user")
                .distinct()
            )
            stages.append(
                {
                    "stage": stage,
                    "label": label,
                    "membership": chosen.get(stage),
                    "candidates": [
                        {
                            "id": person.id,
                            "name": person.user.full_name or person.user.email,
                            "has_signature": current_signature(person) is not None,
                        }
                        for person in people
                    ],
                }
            )
        return {"stages": stages}

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(self._state())

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def put(self, request):
        state = {item["stage"]: item for item in self._state()["stages"]}
        for stage, membership in request.data.items():
            if stage not in state:
                raise exceptions.ValidationError({stage: ["Not a stage with a signatory."]})
            if membership is None:
                Signatory.objects.filter(stage=stage).delete()
                continue
            person = next(
                (item for item in state[stage]["candidates"] if str(item["id"]) == str(membership)),
                None,
            )
            if person is None:
                raise exceptions.ValidationError({stage: ["Choose someone in this stage's role."]})
            if not person["has_signature"]:
                raise exceptions.ValidationError({stage: ["This person has no signature on file."]})
            Signatory.objects.update_or_create(
                stage=stage, defaults={"membership_id": person["id"]}
            )
        record_event(
            "signatories.updated", actor=request.user, metadata={"stages": sorted(request.data)}
        )
        return Response(self._state())


class MemberCodeSettingsView(APIView):
    permission_classes = [IsAuthenticated, require_permission("settings.member_code")]

    @extend_schema(responses={200: MemberCodeSettingsSerializer})
    def get(self, request):
        return Response(MemberCodeSettingsSerializer(services.code_settings()).data)

    @extend_schema(
        request=MemberCodeSettingsSerializer, responses={200: MemberCodeSettingsSerializer}
    )
    def put(self, request):
        settings = services.code_settings()
        serializer = MemberCodeSettingsSerializer(settings, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_event(
            "member_code.settings_updated",
            actor=request.user,
            target=settings,
            metadata=serializer.data,
        )
        return Response(serializer.data)


class FormListsView(APIView):
    """The form's dropdown lists, each as the organization words and orders it."""

    permission_classes = [IsAuthenticated, require_permission("settings.form_lists")]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response({"lists": form_lists.overview()})


class FormListView(APIView):
    permission_classes = [IsAuthenticated, require_permission("settings.form_lists")]

    @extend_schema(
        request=FormListSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: ErrorResponseSerializer},
    )
    def put(self, request, key):
        serializer = FormListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        options = serializer.validated_data["options"]
        form_lists.save(
            key, options, female_only=services.organization_profile().members_female_only
        )
        record_event(
            "form_list.updated",
            actor=request.user,
            metadata={
                "list": key,
                "options": len(options),
                "retired": sum(not option["is_active"] for option in options),
            },
        )
        return Response({"lists": form_lists.overview()})


class BankBranchViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """
    The bank master. Anyone filling forms may read it; changing it is an
    administrator's job.
    """

    serializer_class = BankBranchSerializer
    filterset_fields = ["is_active"]
    search_fields = ["ifsc", "name", "bank__name", "district"]
    ordering_fields = {"ifsc": "ifsc", "bank_name": "bank__name", "branch_name": "name"}
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return BankBranch.objects.select_related("bank").order_by("bank__name", "name")

    def get_permissions(self):
        if self.action in ("list", "retrieve", "by_ifsc"):
            return [IsAuthenticated(), require_permission("applications.view")()]
        return [IsAuthenticated(), require_permission("settings.banks")()]

    def perform_create(self, serializer):
        branch = serializer.save()
        record_event("bank_branch.created", actor=self.request.user, target=branch)

    def perform_update(self, serializer):
        branch = serializer.save()
        record_event(
            "bank_branch.updated",
            actor=self.request.user,
            target=branch,
            metadata={"fields": sorted(serializer.validated_data)},
        )

    @extend_schema(responses={200: BankBranchLookupSerializer, 404: ErrorResponseSerializer})
    @action(detail=False, url_path=r"by-ifsc/(?P<ifsc>[A-Za-z0-9]{11})")
    def by_ifsc(self, request, ifsc):
        branch = banks.by_ifsc(ifsc)
        if branch is None:
            raise exceptions.NotFound("No branch in use has this IFSC.")
        return Response(BankBranchLookupSerializer(branch).data)

    @extend_schema(
        request={"multipart/form-data": BankImportSerializer},
        responses={200: BankImportResultSerializer, 400: ErrorResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_file(self, request):
        serializer = BankImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = banks.import_branches(banks.read_rows(serializer.validated_data["file"].read()))
        record_event(
            "bank_branch.imported",
            actor=request.user,
            metadata={key: result[key] for key in ("created", "updated", "skipped")},
        )
        return Response(result)
