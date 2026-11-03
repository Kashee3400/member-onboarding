from django.http import Http404, HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.core.exceptions import ErrorResponseSerializer
from apps.rbac.permissions import require_permission

from . import services
from .serializers import BrandingImageSerializer, BrandingSerializer, BrandingUpdateSerializer

IMAGE_MAX_AGE = 60 * 60 * 24 * 365
MANAGE = "settings.branding"


def _described(request, branding) -> dict:
    organization = request.user.active_membership.organization
    return BrandingSerializer(
        services.describe(organization, branding, name=organization.name)
    ).data


class PublicBrandingView(APIView):
    """The login page needs this before anyone has signed in."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        auth=[],
        parameters=[OpenApiParameter("organization", str, required=False)],
        responses={200: BrandingSerializer},
    )
    def get(self, request):
        data = services.public_branding(request.query_params.get("organization", ""))
        response = Response(BrandingSerializer(data).data)
        response["Cache-Control"] = "public, max-age=60"
        return response


class PublicBrandingImageView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        auth=[],
        operation_id="public_branding_image",
        parameters=[OpenApiParameter("v", str, required=False)],
        responses={(200, "image/*"): OpenApiTypes.BINARY, 404: ErrorResponseSerializer},
    )
    def get(self, request, slug, kind):
        found = services.public_image(slug, kind)
        if found is None:
            raise Http404
        content, content_type = found
        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = f"public, max-age={IMAGE_MAX_AGE}, immutable"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class BrandingView(APIView):
    permission_classes = [IsAuthenticated, require_permission(MANAGE)]

    @extend_schema(responses={200: BrandingSerializer})
    def get(self, request):
        branding = services.branding_for(request.user.active_membership)
        return Response(_described(request, branding))

    @extend_schema(
        request=BrandingUpdateSerializer,
        responses={200: BrandingSerializer, 400: ErrorResponseSerializer},
    )
    def patch(self, request):
        branding = services.branding_for(request.user.active_membership)
        serializer = BrandingUpdateSerializer(branding, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        branding = serializer.save()
        record_event(
            "branding.updated",
            actor=request.user,
            target=branding,
            metadata=serializer.validated_data,
        )
        return Response(_described(request, branding))


class BrandingImageView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, require_permission(MANAGE)]

    @extend_schema(
        request={"multipart/form-data": BrandingImageSerializer},
        responses={200: BrandingSerializer, 400: ErrorResponseSerializer},
    )
    def post(self, request, kind):
        serializer = BrandingImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branding = services.set_image(
            services.branding_for(request.user.active_membership),
            kind,
            raw=serializer.validated_data["file"].read(),
            actor=request.user,
        )
        return Response(_described(request, branding))

    @extend_schema(request=None, responses={200: BrandingSerializer})
    def delete(self, request, kind):
        branding = services.remove_image(
            services.branding_for(request.user.active_membership), kind, actor=request.user
        )
        return Response(_described(request, branding))
