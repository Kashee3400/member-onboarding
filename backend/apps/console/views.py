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
    ConsoleOrganizationSerializer,
    OrganizationCreatedSerializer,
    OrganizationCreateSerializer,
    OrganizationUpdateSerializer,
)
from .services import create_organization, set_active


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
        set_active(
            organization,
            serializer.validated_data["is_active"],
            actor=request.user,
            own_organization_id=request.user.active_membership.organization_id,
        )
        return Response(_described(organization))
