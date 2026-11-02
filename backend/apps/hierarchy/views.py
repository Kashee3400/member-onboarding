from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, status, viewsets
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
from .models import Bmc, Mcc, MccAssignment, Mpp, Plant, Responsibility, Route
from .serializers import (
    AssignMccSerializer,
    AssignMppSerializer,
    BmcSerializer,
    MccAssignmentSerializer,
    MccSerializer,
    MppAssignmentSerializer,
    MppImportResultSerializer,
    MppImportSerializer,
    MppSerializer,
    PlantSerializer,
    RouteSerializer,
)
from .services import (
    REQUIRED_PERMISSION,
    accessible_mpps,
    assign_mcc,
    assign_mpp,
    end_assignment,
    end_mcc_assignment,
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


class MppViewSet(_MasterViewSet):
    """Reads are limited to the MPPs the caller can access."""

    serializer_class = MppSerializer
    filterset_fields = ["mcc", "route", "is_active"]
    search_fields = ["code", "source_code", "name", "village_code"]
    ordering_fields = ["code", "name", "village_code", "created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Mpp.objects.none()
        user = self.request.user
        return accessible_mpps(user.active_membership, user.active_permissions)

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
