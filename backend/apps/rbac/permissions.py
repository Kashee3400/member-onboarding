from rest_framework.permissions import BasePermission

from .catalog import PERMISSIONS


def require_permission(*codes: str) -> type[BasePermission]:
    """Allows whoever holds any one of `codes`."""
    for code in codes:
        if code not in PERMISSIONS:
            raise ValueError(f"Unknown permission: {code}")

    class RequiredPermission(BasePermission):
        def has_permission(self, request, view):
            held = getattr(request.user, "active_permissions", frozenset())
            return any(code in held for code in codes)

    return RequiredPermission
