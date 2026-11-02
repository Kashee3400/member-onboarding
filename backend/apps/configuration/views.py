from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import ErrorResponseSerializer
from apps.rbac.permissions import require_permission

from .models import IntegrationConfig
from .schemas import INTEGRATION_SCHEMAS
from .serializers import IntegrationReadSerializer, IntegrationWriteSerializer


def _present(kind: str, integration: IntegrationConfig | None) -> dict:
    if integration is None:
        return {"kind": kind, "is_enabled": False, "config": {}, "configured_secrets": []}
    return {
        "kind": kind,
        "is_enabled": integration.is_enabled,
        "config": integration.config,
        "configured_secrets": sorted(integration.get_secrets()),
    }


class IntegrationListView(APIView):
    permission_classes = [IsAuthenticated, require_permission("settings.manage")]
    pagination_class = None

    @extend_schema(
        responses={200: IntegrationReadSerializer(many=True), 403: ErrorResponseSerializer}
    )
    def get(self, request):
        stored = {item.kind: item for item in IntegrationConfig.objects.all()}
        data = [_present(kind, stored.get(kind)) for kind in INTEGRATION_SCHEMAS]
        return Response(IntegrationReadSerializer(data, many=True).data)


KIND_PARAMETER = OpenApiParameter(
    "kind", str, OpenApiParameter.PATH, enum=sorted(INTEGRATION_SCHEMAS)
)


class IntegrationDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("settings.manage")]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if kwargs["kind"] not in INTEGRATION_SCHEMAS:
            raise Http404

    @extend_schema(
        parameters=[KIND_PARAMETER],
        responses={200: IntegrationReadSerializer, 403: ErrorResponseSerializer},
    )
    def get(self, request, kind):
        integration = IntegrationConfig.objects.filter(kind=kind).first()
        return Response(IntegrationReadSerializer(_present(kind, integration)).data)

    @extend_schema(
        parameters=[KIND_PARAMETER],
        request=IntegrationWriteSerializer,
        responses={
            200: IntegrationReadSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    )
    def put(self, request, kind):
        serializer = IntegrationWriteSerializer(data=request.data, context={"kind": kind})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        integration = IntegrationConfig.objects.select_for_update().filter(kind=kind).first()
        if integration is None:
            integration = IntegrationConfig(
                organization=request.user.active_membership.organization, kind=kind
            )

        if "is_enabled" in data:
            integration.is_enabled = data["is_enabled"]
        if "config" in data:
            integration.config = data["config"]
        if "secrets" in data:
            merged = integration.get_secrets()
            for name, value in data["secrets"].items():
                if value is None:
                    merged.pop(name, None)
                else:
                    merged[name] = value
            integration.set_secrets(merged)
        integration.save()

        record_event(
            "integration.updated",
            actor=request.user,
            target=integration,
            # Names only: the values themselves must never reach the audit log.
            metadata={"changed": sorted(data), "secrets": sorted(data.get("secrets", {}))},
        )
        return Response(IntegrationReadSerializer(_present(kind, integration)).data)
