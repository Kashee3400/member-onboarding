from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import ErrorResponseSerializer
from apps.organizations.models import Membership
from apps.rbac.catalog import APPROVAL_PERMISSIONS
from apps.rbac.permissions import require_permission
from apps.rbac.services import permissions_for

from .imports import import_masters, read_rows
from .models import (
    Bmc,
    District,
    Hamlet,
    Mcc,
    MccAssignment,
    MccCover,
    Mpp,
    Plant,
    Responsibility,
    Route,
    State,
    Tehsil,
    Village,
)
from .serializers import (
    AssignMccSerializer,
    AssignMppSerializer,
    BmcSerializer,
    DistrictSerializer,
    GiveCoverSerializer,
    HamletSerializer,
    MccAssignmentSerializer,
    MccCoverSerializer,
    MccSerializer,
    MppAssignmentSerializer,
    MppImportResultSerializer,
    MppImportSerializer,
    MppSerializer,
    PlantSerializer,
    RouteSerializer,
    StateSerializer,
    TehsilNameSerializer,
    TehsilSerializer,
    VillageSerializer,
)
from .services import (
    PLACE_RELATED,
    REQUIRED_PERMISSION,
    CoverError,
    PlaceClash,
    accessible_mpps,
    assign_mcc,
    assign_mpp,
    end_assignment,
    end_cover,
    end_mcc_assignment,
    follow_master,
    give_cover,
)


class _MasterViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        code = "hierarchy.view" if self.request.method in ("GET", "HEAD") else "hierarchy.manage"
        return [IsAuthenticated(), require_permission(code)()]

    def perform_create(self, serializer):
        serializer.save(organization_id=self.request.user.active_membership.organization_id)


class PlantViewSet(_MasterViewSet):
    queryset = Plant.objects.all()
    serializer_class = PlantSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]


class MccViewSet(_MasterViewSet):
    serializer_class = MccSerializer
    filterset_fields = ["plant", "is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]

    def get_queryset(self):
        held = MccAssignment.objects.filter(ended_at__isnull=True)
        return (
            Mcc.objects.select_related("plant")
            .annotate(mpp_count=Count("mpps", filter=Q(mpps__is_active=True), distinct=True))
            .prefetch_related(
                Prefetch(
                    "assignments",
                    queryset=held.select_related("membership__user").prefetch_related(
                        "membership__role_links__role"
                    ),
                    to_attr="open_assignments",
                )
            )
        )

    def get_permissions(self):
        if self.action == "area_manager":
            code = "hierarchy.view" if self.request.method == "GET" else "mpp.assign"
            return [IsAuthenticated(), require_permission(code)()]
        return super().get_permissions()

    @extend_schema(
        methods=["GET"],
        request=None,
        responses={200: MccAssignmentSerializer(many=True)},
    )
    @extend_schema(
        methods=["POST"],
        request=AssignMccSerializer,
        responses={201: MccAssignmentSerializer, 400: ErrorResponseSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="area-manager", pagination_class=None)
    def area_manager(self, request, pk=None):
        """Whoever holds an MCC reaches all its MPPs and their forms at once."""
        mcc = self.get_object()
        if request.method == "GET":
            history = mcc.assignments.select_related("membership__user").prefetch_related(
                "membership__role_links__role"
            )
            return Response(MccAssignmentSerializer(history, many=True).data)

        serializer = AssignMccSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = serializer.validated_data["membership"]
        if not APPROVAL_PERMISSIONS & permissions_for(membership):
            raise exceptions.ValidationError(
                {"membership": ["This person does not approve forms."]}
            )

        assignment = assign_mcc(mcc=mcc, membership=membership, actor=request.user)
        return Response(MccAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class MccCoverViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Someone works a colleague's MCCs while they are away. Ended covers stay as history."""

    serializer_class = MccCoverSerializer
    search_fields = ["absent__user__full_name", "colleague__user__full_name", "reason"]
    ordering_fields = ["starts_on", "ends_on", "created_at"]

    def get_permissions(self):
        code = "hierarchy.view" if self.request.method in ("GET", "HEAD") else "mpp.assign"
        return [IsAuthenticated(), require_permission(code)()]

    def get_queryset(self):
        held = MccAssignment.objects.filter(ended_at__isnull=True).select_related("mcc")
        covers = MccCover.objects.select_related(
            "absent__user", "colleague__user", "given_by", "ended_by"
        ).prefetch_related(Prefetch("absent__mcc_assignments", queryset=held, to_attr="open_mccs"))
        today = timezone.localdate()
        state = self.request.query_params.get("state")
        if state == "current":
            return covers.filter(ended_at__isnull=True, ends_on__gte=today)
        if state == "past":
            return covers.filter(Q(ended_at__isnull=False) | Q(ends_on__lt=today))
        return covers

    @extend_schema(parameters=[OpenApiParameter("state", str, enum=["current", "past"])])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=GiveCoverSerializer,
        responses={201: MccCoverSerializer, 400: ErrorResponseSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = GiveCoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cover = give_cover(**serializer.validated_data, actor=request.user)
        except CoverError as exc:
            raise exceptions.ValidationError({"detail": [str(exc)]}) from exc
        return Response(
            MccCoverSerializer(self.get_queryset().get(pk=cover.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses={204: None, 404: ErrorResponseSerializer})
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        """Stop it now, or call it off before it begins."""
        if not end_cover(cover=self.get_object(), actor=request.user):
            raise exceptions.NotFound("This cover is already over.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class BmcViewSet(_MasterViewSet):
    queryset = Bmc.objects.select_related("mcc")
    serializer_class = BmcSerializer
    filterset_fields = ["mcc", "is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]


class RouteViewSet(_MasterViewSet):
    queryset = Route.objects.select_related("bmc__mcc")
    serializer_class = RouteSerializer
    filterset_fields = {"bmc": ["exact"], "bmc__mcc": ["exact"], "is_active": ["exact"]}
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]


class _PlaceViewSet(_MasterViewSet):
    """
    A location master, filled only from the ERP by the masters import, so it never
    drifts from the codes member codes are built from. Read-only here.
    """

    http_method_names = ["get", "head", "options"]
    kind = ""

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("hierarchy.view", "locations.view")()]

    search_fields = ["code", "name", "name_hi"]
    ordering_fields = ["code", "name", "created_at"]

    def perform_update(self, serializer):
        place = serializer.save()
        try:
            follow_master(self.kind, place)
        except PlaceClash as exc:
            raise exceptions.ValidationError({"code": [str(exc)]}) from exc


class StateViewSet(_PlaceViewSet):
    kind = "state"
    queryset = State.objects.all()
    serializer_class = StateSerializer
    filterset_fields = ["is_active"]


class DistrictViewSet(_PlaceViewSet):
    kind = "district"
    queryset = District.objects.select_related("state")
    serializer_class = DistrictSerializer
    filterset_fields = ["state", "is_active"]


class TehsilViewSet(_PlaceViewSet):
    """The ERP has tehsil codes but no names, so a tehsil's name is the one thing set here."""

    http_method_names = ["get", "patch", "head", "options"]
    kind = "tehsil"

    def get_serializer_class(self):
        return TehsilNameSerializer if self.action == "partial_update" else TehsilSerializer

    queryset = Tehsil.objects.select_related("district")
    serializer_class = TehsilSerializer
    filterset_fields = {
        "district": ["exact"],
        "district__state": ["exact"],
        "is_active": ["exact"],
    }


class VillageViewSet(_PlaceViewSet):
    kind = "village"
    queryset = Village.objects.select_related("tehsil")
    serializer_class = VillageSerializer
    filterset_fields = {
        "tehsil": ["exact"],
        "tehsil__district": ["exact"],
        "is_active": ["exact"],
    }


class HamletViewSet(_PlaceViewSet):
    kind = "hamlet"
    queryset = Hamlet.objects.select_related("village")
    serializer_class = HamletSerializer
    filterset_fields = ["village", "is_active"]


class MppViewSet(_MasterViewSet):
    """Reads are limited to the MPPs the caller can access."""

    serializer_class = MppSerializer
    filterset_fields = ["mcc", "route", "village", "is_active"]
    search_fields = ["code", "source_code", "name", "village_code", "village_name"]
    ordering_fields = ["code", "name", "village_code", "created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Mpp.objects.none()
        user = self.request.user
        mpps = accessible_mpps(user.active_membership, user.active_permissions)
        return mpps.select_related(*PLACE_RELATED)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        if self.action == "assignments":
            code = "hierarchy.view" if self.request.method == "GET" else "mpp.assign"
            return [IsAuthenticated(), require_permission(code)()]
        return super().get_permissions()

    @extend_schema(
        methods=["GET"],
        responses={200: MppAssignmentSerializer(many=True)},
        description="Full handover history, newest first.",
    )
    @extend_schema(
        methods=["POST"],
        request=AssignMppSerializer,
        responses={201: MppAssignmentSerializer, 400: ErrorResponseSerializer},
        description="Assign the MPP, transferring it from anyone who holds the responsibility.",
    )
    @action(detail=True, methods=["get", "post"], pagination_class=None, filterset_fields=[])
    def assignments(self, request, pk=None):
        # Not limited to accessible MPPs: an MPP may have nobody on it yet.
        mpp = get_object_or_404(Mpp, pk=pk)
        if request.method == "GET":
            history = mpp.assignments.select_related("membership__user")
            return Response(MppAssignmentSerializer(history, many=True).data)

        serializer = AssignMppSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = serializer.validated_data["membership"]
        responsibility = serializer.validated_data["responsibility"]

        if REQUIRED_PERMISSION[responsibility] not in permissions_for(membership):
            raise exceptions.ValidationError(
                {"membership": ["This person's role does not allow that responsibility."]}
            )

        assignment = assign_mpp(
            mpp=mpp, membership=membership, responsibility=responsibility, actor=request.user
        )
        return Response(MppAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class MppImportView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, require_permission("hierarchy.manage")]

    @extend_schema(
        request={"multipart/form-data": MppImportSerializer},
        responses={200: MppImportResultSerializer, 400: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = MppImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = import_masters(read_rows(serializer.validated_data["file"].read()))
        if not result["problems"]:
            record_event(
                "hierarchy.imported",
                actor=request.user,
                metadata={"created": result["created"], "updated": result["updated"]},
            )
        return Response(result)


class MccAssignmentEndView(APIView):
    permission_classes = [IsAuthenticated, require_permission("mpp.assign")]

    @extend_schema(request=None, responses={204: None, 404: ErrorResponseSerializer})
    def post(self, request, pk, membership):
        mcc = get_object_or_404(Mcc, pk=pk)
        person = get_object_or_404(Membership, pk=membership)
        if not end_mcc_assignment(mcc=mcc, membership=person, actor=request.user):
            raise exceptions.NotFound("This person does not hold this MCC.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MppAssignmentEndView(APIView):
    permission_classes = [IsAuthenticated, require_permission("mpp.assign")]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "responsibility", str, OpenApiParameter.PATH, enum=Responsibility.values
            )
        ],
        responses={204: None, 404: ErrorResponseSerializer},
    )
    def delete(self, request, pk, responsibility):
        if responsibility not in Responsibility.values:
            raise exceptions.NotFound()
        mpp = get_object_or_404(Mpp, pk=pk)
        if not end_assignment(mpp=mpp, responsibility=responsibility, actor=request.user):
            raise exceptions.NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
