from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.tenancy import activate_organization
from apps.rbac.services import permissions_for, requires_mfa

from .models import Membership


class MfaRequired(exceptions.AuthenticationFailed):
    default_detail = "Multi-factor authentication is required."
    default_code = "mfa_required"


class PasswordChangeRequired(exceptions.APIException):
    status_code = 403
    default_detail = "Set a new password first."
    default_code = "password_change_required"


# All a temporary password can do is be replaced, or sign out.
TEMPORARY_PASSWORD_PATHS = ("/api/v1/auth/password/change/", "/api/v1/auth/logout/")


class OrganizationJWTAuthentication(JWTAuthentication):
    """
    Validates the token, then the membership, on every request, so removing
    someone from an organization takes effect immediately.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        organization_id = token.get("org")
        if not organization_id:
            raise exceptions.AuthenticationFailed("Token has no organization.")

        activate_organization(organization_id)
        membership = (
            Membership.objects.select_related("organization")
            .filter(user=user, is_active=True, organization__is_active=True)
            .first()
        )
        if membership is None:
            raise exceptions.AuthenticationFailed("No active organization membership.")

        if not token.get("mfa") and requires_mfa(membership):
            raise MfaRequired()

        if user.must_change_password and request.path not in TEMPORARY_PASSWORD_PATHS:
            raise PasswordChangeRequired()

        user.active_membership = membership
        user.active_permissions = permissions_for(membership)
        return user, token
