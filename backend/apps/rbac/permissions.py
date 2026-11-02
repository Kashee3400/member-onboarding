from rest_framework.permissions import BasePermission

from .catalog import PERMISSIONS


def require_permission(code: str) -> type[BasePermission]:
    if code not in PERMISSIONS:
        raise ValueError(f"Unknown permission: {code}")

    class RequiredPermission(BasePermission):
        def has_permission(self, request, view):
            return code in getattr(request.user, "active_permissions", frozenset())

    return RequiredPermission
