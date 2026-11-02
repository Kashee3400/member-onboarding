import structlog
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from apps.audit.services import record_event
from apps.core.exceptions import ErrorResponseSerializer, error_body
from apps.core.tenancy import organization_context
from apps.rbac.permissions import require_permission

from .models import TrustedIssuer
from .serializers import (
    ExchangeRequestSerializer,
    ExchangeResponseSerializer,
    TrustedIssuerSerializer,
)
from .services import AssertionRejected, resolve_membership, sync_mpp_assignments, verify_assertion

logger = structlog.get_logger(__name__)


def _rejected():
    return Response(
        error_body("invalid_assertion", "This sign-in could not be accepted."),
        status=status.HTTP_401_UNAUTHORIZED,
    )


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class ExchangeView(APIView):
    """
    Swaps a host application's short-lived signed assertion for an access token.

    No refresh token is issued: the app comes back through its host, so disabling
    someone there, or moving an MPP, takes effect within one access token lifetime.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "exchange"

    @extend_schema(
        auth=[],
        request=ExchangeRequestSerializer,
        responses={200: ExchangeResponseSerializer, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = ExchangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            assertion = verify_assertion(serializer.validated_data["assertion"])
        except AssertionRejected as exc:
            logger.warning("federation_assertion_rejected", reason=str(exc))
            return _rejected()

        issuer = assertion.issuer
        try:
            with organization_context(issuer.organization_id):
                membership = resolve_membership(assertion)
                if membership is None:
                    record_event(
                        "federation.exchange.refused", metadata={"subject": assertion.subject}
                    )
                    return _rejected()

                user = membership.user
                if issuer.syncs_mpp_assignments:
                    sync_mpp_assignments(membership, assertion.mpp_codes, actor=user)
        except IntegrityError:
            # Two first sign-ins raced; the winner's identity exists on the next attempt.
            return _rejected()

        access = AccessToken.for_user(user)
        access["org"] = str(issuer.organization_id)
        return Response(
            {
                "access": str(access),
                "expires_in": int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            }
        )


class TrustedIssuerViewSet(viewsets.ModelViewSet):
    serializer_class = TrustedIssuerSerializer
    permission_classes = [IsAuthenticated, require_permission("settings.manage")]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TrustedIssuer.objects.none()
        organization_id = self.request.user.active_membership.organization_id
        return TrustedIssuer.objects.filter(organization_id=organization_id)

    def perform_create(self, serializer):
        issuer = serializer.save(
            organization_id=self.request.user.active_membership.organization_id
        )
        record_event("federation.issuer.created", actor=self.request.user, target=issuer)

    def perform_update(self, serializer):
        issuer = serializer.save()
        record_event(
            "federation.issuer.updated",
            actor=self.request.user,
            target=issuer,
            metadata={"changed": sorted(serializer.validated_data)},
        )
