from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from apps.audit.services import record_event
from apps.core.exceptions import Conflict, ErrorResponseSerializer, error_body
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership, Organization

from .mfa import (
    MfaChallengeToken,
    confirm_enrollment,
    consume_attempt,
    consume_challenge,
    issue_tokens,
    start_enrollment,
    use_recovery_code,
    verify_code,
)
from .models import MfaDevice
from .serializers import (
    MfaConfirmResponseSerializer,
    MfaConfirmSerializer,
    MfaEnrollResponseSerializer,
    MfaEnrollSerializer,
    MfaVerifySerializer,
    TokenPairSerializer,
)


def _rejected():
    return Response(
        error_body("invalid_mfa", "Invalid or expired verification."),
        status=status.HTTP_401_UNAUTHORIZED,
    )


class _ChallengeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa"

    def resolve(self, raw_token):
        """Returns (challenge, user, organization), or None unless all are still valid."""
        try:
            challenge = MfaChallengeToken(raw_token)
        except TokenError:
            return None

        user = get_user_model().objects.filter(pk=challenge["user_id"], is_active=True).first()
        organization = Organization.objects.filter(pk=challenge["org"], is_active=True).first()
        if user is None or organization is None:
            return None

        with organization_context(organization.id):
            member = Membership.objects.filter(user=user, is_active=True).exists()
        return (challenge, user, organization) if member else None


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class MfaVerifyView(_ChallengeView):
    """Failed attempts must survive in the audit log, so this view manages its own commits."""

    @extend_schema(
        auth=[],
        request=MfaVerifySerializer,
        responses={200: TokenPairSerializer, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = MfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        resolved = self.resolve(data["mfa_token"])
        if resolved is None:
            return _rejected()
        challenge, user, organization = resolved

        if not consume_attempt(challenge):
            return _rejected()

        with organization_context(organization.id):
            with transaction.atomic():
                device = (
                    MfaDevice.objects.select_for_update()
                    .filter(user=user, confirmed_at__isnull=False)
                    .first()
                )
                if device is None:
                    accepted = False
                elif data.get("code"):
                    accepted = verify_code(device, data["code"])
                else:
                    accepted = use_recovery_code(user, data["recovery_code"])

            if not accepted or not consume_challenge(challenge):
                record_event("auth.mfa.failed", actor=user)
                return _rejected()

            method = "code" if data.get("code") else "recovery_code"
            record_event("auth.login.succeeded", actor=user, metadata={"mfa": method})
            return Response(issue_tokens(user, organization, mfa=True))


class MfaEnrollView(_ChallengeView):
    @extend_schema(
        auth=[],
        request=MfaEnrollSerializer,
        responses={
            200: MfaEnrollResponseSerializer,
            401: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    def post(self, request):
        serializer = MfaEnrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resolved = self.resolve(serializer.validated_data["mfa_token"])
        if resolved is None:
            return _rejected()
        _, user, _ = resolved

        # Otherwise a stolen password could replace the owner's authenticator.
        if MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).exists():
            raise Conflict("MFA is already set up. Ask an admin to reset it.")

        return Response(start_enrollment(user))


class MfaConfirmView(_ChallengeView):
    @extend_schema(
        auth=[],
        request=MfaConfirmSerializer,
        responses={200: MfaConfirmResponseSerializer, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = MfaConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        resolved = self.resolve(data["mfa_token"])
        if resolved is None:
            return _rejected()
        challenge, user, organization = resolved

        if not consume_attempt(challenge):
            return _rejected()

        device = (
            MfaDevice.objects.select_for_update()
            .filter(user=user, confirmed_at__isnull=True)
            .first()
        )
        codes = confirm_enrollment(device, data["code"]) if device else None
        if codes is None or not consume_challenge(challenge):
            return _rejected()

        with organization_context(organization.id):
            record_event("mfa.enrolled", actor=user)
            record_event("auth.login.succeeded", actor=user, metadata={"mfa": "enrollment"})
        return Response({**issue_tokens(user, organization, mfa=True), "recovery_codes": codes})
