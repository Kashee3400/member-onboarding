from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.organizations.models import Organization

from .health import organization_health
from .permissions import IsPlatformOperator
from .serializers import (
    ApplicationDeletedSerializer,
    ApplicationDeleteSerializer,
    ConsoleOrganizationSerializer,
    OrganizationCreatedSerializer,
    OrganizationCreateSerializer,
    OrganizationUpdateSerializer,
)
from .services import create_organization, delete_application, set_active, set_storage_limit


def _described(organization) -> dict:
    return {
        "id": organization.id,
        "name": organization.name,
        "slug": organization.slug,
        "is_active": organization.is_active,
        "created_at": organization.created_at,
        "health": organization_health(organization),
    }


class ConsoleOrganizationsView(APIView):
    """Every organization on the platform, with its health. For platform operators only."""

    permission_classes = [IsAuthenticated, IsPlatformOperator]

    @extend_schema(responses={200: ConsoleOrganizationSerializer(many=True)})
    def get(self, request):
        organizations = Organization.objects.order_by("name")
        return Response([_described(organization) for organization in organizations])

    @extend_schema(
        request=OrganizationCreateSerializer,
        responses={201: OrganizationCreatedSerializer, 400: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = create_organization(**serializer.validated_data, actor=request.user)
        body = {
            "organization": _described(created["organization"]),
            "invitation_link": created["invitation_link"],
        }
        return Response(body, status=status.HTTP_201_CREATED)


class ConsoleOrganizationView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOperator]

    @extend_schema(
        request=OrganizationUpdateSerializer,
        responses={200: ConsoleOrganizationSerializer, 400: ErrorResponseSerializer},
    )
    def patch(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        serializer = OrganizationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "is_active" in data:
            set_active(
                organization,
                data["is_active"],
                actor=request.user,
                own_organization_id=request.user.active_membership.organization_id,
            )
        if "storage_limit_mb" in data:
            set_storage_limit(organization, data["storage_limit_mb"], actor=request.user)
        return Response(_described(organization))


class ConsoleApplicationDeleteView(APIView):
    """
    Removes one form of the organization signed in to, completely. For the platform
    operator only, to let a form be filled again from the start.
    """

    permission_classes = [IsAuthenticated, IsPlatformOperator]

    @extend_schema(
        request=ApplicationDeleteSerializer,
        responses={200: ApplicationDeletedSerializer, 404: ErrorResponseSerializer},
    )
    def post(self, request, pk):
        from apps.applications.models import Application

        serializer = ApplicationDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = get_object_or_404(Application.objects.select_related("mpp"), pk=pk)
        summary = delete_application(
            application, actor=request.user, reason=serializer.validated_data["reason"].strip()
        )
        return Response(summary)
