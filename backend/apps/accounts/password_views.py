import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.audit.services import record_event
from apps.core.exceptions import ErrorResponseSerializer
from apps.core.tenancy import organization_context
from apps.notifications.tasks import send_password_reset
from apps.organizations.models import Membership, Organization

from .mfa import issue_tokens
from .serializers import TokenPairSerializer


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordForgotSerializer(serializers.Serializer):
    email = serializers.EmailField()
    organization = serializers.SlugField()


class PasswordResetSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


def _set_password(user, password: str) -> None:
    """Every other session ends, in case the old password was the problem."""
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise exceptions.ValidationError({"new_password": exc.messages}) from exc

    user.set_password(password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password", "updated_at"])
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def issue_temporary_password(user) -> str:
    """For someone locked out. It works once: their next login must replace it."""
    password = secrets.token_urlsafe(12)
    user.set_password(password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password", "updated_at"])
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)
    return password


class PasswordChangeView(APIView):
    @extend_schema(
        request=PasswordChangeSerializer,
        responses={200: TokenPairSerializer, 400: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        if not user.check_password(data["current_password"]):
            raise exceptions.ValidationError({"current_password": ["This is not correct."]})
        if data["new_password"] == data["current_password"]:
            raise exceptions.ValidationError({"new_password": ["Choose a different password."]})

        _set_password(user, data["new_password"])
        record_event("auth.password_changed", actor=user)
        organization = user.active_membership.organization
        return Response(issue_tokens(user, organization, mfa=bool(request.auth.get("mfa"))))


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class PasswordForgotView(APIView):
    """Answers the same either way, so nobody can test which accounts exist."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(auth=[], request=PasswordForgotSerializer, responses={202: None})
    def post(self, request):
        serializer = PasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = get_user_model().objects.filter(email=data["email"].strip().lower()).first()
        organization = Organization.objects.filter(
            slug=data["organization"], is_active=True
        ).first()

        if user and organization and user.is_active and user.has_usable_password():
            with organization_context(organization.id):
                member = Membership.objects.filter(user=user, is_active=True).exists()
            if member:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                link = f"{settings.PORTAL_URL}/reset-password?uid={uid}&token={token}"
                send_password_reset.delay(str(organization.id), user.email, link)

        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        auth=[],
        request=PasswordResetSerializer,
        responses={204: None, 400: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invalid = exceptions.ValidationError({"token": ["This link is invalid or has expired."]})
        try:
            user_id = force_str(urlsafe_base64_decode(data["uid"]))
            user = get_user_model().objects.get(pk=user_id)
        except (ValueError, TypeError, DjangoValidationError, get_user_model().DoesNotExist) as exc:
            raise invalid from exc
        if not default_token_generator.check_token(user, data["token"]):
            raise invalid

        _set_password(user, data["new_password"])
        record_event("auth.password_reset", actor=user)
        return Response(status=status.HTTP_204_NO_CONTENT)
