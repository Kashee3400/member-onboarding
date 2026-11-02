from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    PermissionCatalogView,
    PublicInvitationView,
    RoleViewSet,
    StaffDetailView,
    StaffInviteView,
    StaffListView,
    StaffMfaResetView,
    StaffPasswordResetView,
)

router = SimpleRouter()
router.register("roles", RoleViewSet, basename="role")

urlpatterns = [
    path("permissions/", PermissionCatalogView.as_view(), name="permission-list"),
    path("staff/", StaffListView.as_view(), name="staff-list"),
    path("staff/<uuid:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path("staff/<uuid:pk>/invite/", StaffInviteView.as_view(), name="staff-invite"),
    path("public/invitations/", PublicInvitationView.as_view(), name="public-invitation"),
    path("staff/<uuid:pk>/mfa-reset/", StaffMfaResetView.as_view(), name="staff-mfa-reset"),
    path(
        "staff/<uuid:pk>/password-reset/",
        StaffPasswordResetView.as_view(),
        name="staff-password-reset",
    ),
    path("", include(router.urls)),
]
