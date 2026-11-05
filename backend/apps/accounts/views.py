from django.contrib.auth import authenticate
from django.db import transaction
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import record_event
from apps.console.permissions import is_operator
from apps.core.exceptions import ErrorResponseSerializer, error_body
from apps.core.tenancy import organization_context
from apps.documents.services import current_signature, needs_signature
from apps.organizations.models import Membership, Organization
from apps.rbac.services import role_codes_for, role_names_for

from .mfa import login_result
from .serializers import (
    CurrentUserSerializer,
    LoginRequestSerializer,
    LoginResponseSerializer,
    LogoutRequestSerializer,
    RefreshRequestSerializer,
    TokenPairSerializer,
)


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class LoginView(APIView):
    """Issues tokens for one organization. Failed attempts must survive in the audit log."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        auth=[],
        request=LoginRequestSerializer,
        responses={200: LoginResponseSerializer, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = authenticate(
            request, username=data["email"].strip().lower(), password=data["password"]
        )
        organization = Organization.objects.filter(
            slug=data["organization"], is_active=True
        ).first()

        failure_metadata = {"email": data["email"], "organization": data["organization"]}
        if organization:
            with organization_context(organization.id):
                if user and Membership.objects.filter(user=user, is_active=True).exists():
                    return Response(login_result(user, organization))
                record_event("auth.login.failed", metadata=failure_metadata)
        else:
            record_event("auth.login.failed", metadata=failure_metadata)

        return Response(
            # One response for every failure, so accounts and organizations can't be probed.
            error_body("invalid_credentials", "Invalid login details."),
            status=status.HTTP_401_UNAUTHORIZED,
        )


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        auth=[],
        request=RefreshRequestSerializer,
        responses={200: TokenPairSerializer, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError, InvalidToken:
            return Response(
                error_body("invalid_token", "Invalid or expired token."),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(serializer.validated_data)


class LogoutView(APIView):
    @extend_schema(
        request=LogoutRequestSerializer,
        responses={204: None, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = LogoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc
        record_event("auth.logout", actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(responses={200: CurrentUserSerializer, 401: ErrorResponseSerializer})
    def get(self, request):
        membership = request.user.active_membership
        return Response(
            CurrentUserSerializer(
                {
                    "id": request.user.id,
                    "email": request.user.email,
                    "full_name": request.user.full_name,
                    "membership_id": membership.id,
                    "photo_url": membership.photo_url,
                    "has_signature": current_signature(membership) is not None,
                    "needs_signature": needs_signature(membership, request.user.active_permissions),
                    "organization": membership.organization,
                    "roles": sorted(role_codes_for(membership)),
                    "role_names": sorted(role_names_for(membership)),
                    "permissions": sorted(request.user.active_permissions),
                    "platform_operator": is_operator(request),
                }
            ).data
        )
