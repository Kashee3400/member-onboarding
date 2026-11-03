from rest_framework.permissions import BasePermission


def is_operator(request) -> bool:
    """
    Whoever runs the platform for every organization. Deliberately not a role
    permission: an organization's admin could otherwise grant it to themselves.
    Only `make_platform_operator` on the server makes one, and it needs MFA.
    """
    user = request.user
    return bool(
        user and user.is_authenticated and user.is_superuser and (request.auth or {}).get("mfa")
    )


class IsPlatformOperator(BasePermission):
    message = "Only a platform operator, signed in with MFA, may do this."

    def has_permission(self, request, view):
        return is_operator(request)
