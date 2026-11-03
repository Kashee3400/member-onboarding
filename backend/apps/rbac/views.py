from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, ProtectedError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import exceptions, generics, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.mfa import reset_mfa
from apps.accounts.password_views import issue_temporary_password
from apps.applications.models import Signatory
from apps.audit.services import record_event
from apps.branding.services import staff_email_problem
from apps.console.permissions import is_operator
from apps.core.exceptions import Conflict, ErrorResponseSerializer
from apps.core.tenancy import organization_context
from apps.documents.models import StaffSignature
from apps.hierarchy.services import end_assignments_for
from apps.organizations.models import Membership, Organization

from . import invitations
from .catalog import PERMISSIONS
from .models import Role
from .navigation import locked_paths, navigation_for
from .permissions import require_permission
from .serializers import (
    AcceptInvitationSerializer,
    InvitationLinkSerializer,
    InvitationSerializer,
    LockedPagesSerializer,
    NavigationItemSerializer,
    PermissionSerializer,
    RoleSerializer,
    StaffCreateSerializer,
    StaffSerializer,
    StaffUpdateSerializer,
    TemporaryPasswordSerializer,
)
from .services import (
    ensure_can_assign,
    ensure_can_grant,
    ensure_role_manager_remains,
    set_membership_roles,
)


class NavigationView(APIView):
    """The sidebar for the signed-in user, filtered by their permissions."""

    @extend_schema(responses={200: NavigationItemSerializer(many=True)})
    def get(self, request):
        return Response(
            navigation_for(request.user.active_permissions, operator=is_operator(request))
        )


class LockedPagesView(APIView):
    """Portal pages the signed-in user may not open, so a typed URL meets a refusal."""

    @extend_schema(responses={200: LockedPagesSerializer})
    def get(self, request):
        permissions = request.user.active_permissions
        return Response({"paths": locked_paths(permissions, operator=is_operator(request))})


class PermissionCatalogView(APIView):
    permission_classes = [IsAuthenticated, require_permission("roles.view")]

    @extend_schema(responses={200: PermissionSerializer(many=True)})
    def get(self, request):
        return Response(
            [{"code": code, "description": text} for code, text in sorted(PERMISSIONS.items())]
        )


@extend_schema_view(
    create=extend_schema(responses={201: RoleSerializer, 403: ErrorResponseSerializer}),
    partial_update=extend_schema(responses={200: RoleSerializer, 409: ErrorResponseSerializer}),
    update=extend_schema(responses={200: RoleSerializer, 409: ErrorResponseSerializer}),
    destroy=extend_schema(responses={204: None, 409: ErrorResponseSerializer}),
)
class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]

    def get_permissions(self):
        code = "roles.view" if self.request.method in ("GET", "HEAD") else "roles.manage"
        return [IsAuthenticated(), require_permission(code)()]

    def _reject_system_role(self, role):
        if role.is_system:
            raise Conflict("System roles cannot be changed.")

    def perform_create(self, serializer):
        ensure_can_grant(
            self.request.user.active_permissions, serializer.validated_data["permissions"]
        )
        role = serializer.save(organization_id=self.request.user.active_membership.organization_id)
        record_event(
            "role.created",
            actor=self.request.user,
            target=role,
            metadata={"permissions": role.permissions},
        )

    def perform_update(self, serializer):
        self._reject_system_role(serializer.instance)
        ensure_can_grant(
            self.request.user.active_permissions,
            serializer.validated_data.get("permissions", []),
        )
        previous = serializer.instance.permissions
        role = serializer.save()
        ensure_role_manager_remains()
        record_event(
            "role.updated",
            actor=self.request.user,
            target=role,
            metadata={"before": previous, "after": role.permissions},
        )

    def perform_destroy(self, instance):
        self._reject_system_role(instance)
        record_event("role.deleted", actor=self.request.user, target=instance)
        try:
            instance.delete()
        except ProtectedError as exc:
            raise Conflict("This role is still assigned to staff.") from exc


def _staff_queryset():
    current = StaffSignature.objects.filter(membership=OuterRef("pk"), is_current=True)
    signs = Signatory.objects.filter(membership=OuterRef("pk"))
    return (
        Membership.objects.select_related("user")
        .prefetch_related("role_links__role")
        .annotate(signature_on_file=Exists(current), is_signatory=Exists(signs))
    )


class StaffListView(generics.ListAPIView):
    serializer_class = StaffSerializer
    filterset_fields = ["is_active"]
    search_fields = ["user__email", "user__full_name"]
    ordering_fields = {
        "email": "user__email",
        "full_name": "user__full_name",
        "is_active": "is_active",
        "created_at": "created_at",
    }

    def get_queryset(self):
        return _staff_queryset()

    def get_permissions(self):
        code = "staff.view" if self.request.method == "GET" else "staff.manage"
        return [IsAuthenticated(), require_permission(code)()]

    @extend_schema(
        request=StaffCreateSerializer,
        responses={201: StaffSerializer, 409: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        roles = data["role_ids"]

        ensure_can_assign(request.user, roles)

        User = get_user_model()
        email = data["email"].strip().lower()
        if problem := staff_email_problem(email):
            raise exceptions.ValidationError({"email": [problem]})
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(
                email,
                data.get("password"),
                full_name=data["full_name"],
                must_change_password="password" in data,
            )
        elif Membership.objects.filter(user=user).exists():
            raise Conflict("This person is already staff in this organization.")

        membership = Membership.objects.create(
            organization=request.user.active_membership.organization, user=user
        )
        set_membership_roles(membership, roles)
        record_event(
            "staff.created",
            actor=request.user,
            target=membership,
            metadata={"roles": [role.code for role in roles]},
        )
        body = StaffSerializer(_staff_queryset().get(pk=membership.pk)).data
        if invitations.is_pending(membership):
            # Shown to whoever invited them too, for when mail is down or not set up.
            body["invite_link"] = invitations.invite(membership, actor=request.user)
        return Response(body, status=status.HTTP_201_CREATED)


class StaffDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("staff.manage")]

    @extend_schema(
        request=StaffUpdateSerializer,
        responses={
            200: StaffSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    )
    def patch(self, request, pk):
        membership = get_object_or_404(_staff_queryset().select_for_update(of=("self",)), pk=pk)
        serializer = StaffUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "full_name" in data:
            ensure_only_here(membership.user, request.user.active_membership.organization)
            membership.user.full_name = data["full_name"].strip()
            membership.user.save(update_fields=["full_name", "updated_at"])

        old_email = membership.user.email
        if "email" in data and data["email"].strip().lower() != old_email:
            change_email(
                membership.user, data["email"], request.user.active_membership.organization
            )

        if "role_ids" in data:
            ensure_can_assign(request.user, data["role_ids"], membership=membership)
            set_membership_roles(membership, data["role_ids"])

        if "is_active" in data and data["is_active"] != membership.is_active:
            membership.is_active = data["is_active"]
            membership.save(update_fields=["is_active", "updated_at"])
            if not membership.is_active:
                end_assignments_for(membership, actor=request.user)

        ensure_role_manager_remains()
        record_event(
            "staff.updated",
            actor=request.user,
            target=membership,
            metadata={
                "is_active": membership.is_active,
                "roles": sorted(role.code for role in data.get("role_ids", [])),
                **(
                    {"email_from": old_email, "email_to": membership.user.email}
                    if membership.user.email != old_email
                    else {}
                ),
            },
        )
        return Response(StaffSerializer(_staff_queryset().get(pk=membership.pk)).data)


def change_email(user, email, organization) -> None:
    """The email is how they sign in, so it must be theirs alone, and theirs to lose."""
    email = email.strip().lower()
    if problem := staff_email_problem(email):
        raise exceptions.ValidationError({"email": [problem]})
    ensure_only_here(user, organization)
    if get_user_model().objects.filter(email=email).exclude(pk=user.pk).exists():
        raise Conflict("Another account already uses this email.")
    user.email = email
    user.save(update_fields=["email", "updated_at"])


def ensure_only_here(user, organization) -> None:
    """
    An account can serve several organizations, and the password and name are the
    account's. One organization's admin must not be able to change what another relies on.
    """
    for other in Organization.objects.exclude(pk=organization.pk).values_list("pk", flat=True):
        with organization_context(other):
            if Membership.objects.filter(user=user).exists():
                raise Conflict(
                    "This person also works for another organization, so only they can change this."
                )


class StaffPasswordResetView(APIView):
    """
    Gives a locked-out person a one-time password, shown here and nowhere else.
    Their authenticator stays in place, so this alone cannot get an admin into an
    account that needs MFA.
    """

    permission_classes = [IsAuthenticated, require_permission("staff.manage")]

    @extend_schema(
        request=None,
        responses={
            200: TemporaryPasswordSerializer,
            403: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        membership = get_object_or_404(_staff_queryset(), pk=pk)
        user = membership.user
        if user.pk == request.user.pk:
            raise exceptions.PermissionDenied("Change your own password from your account menu.")
        if not user.has_usable_password():
            raise Conflict(
                "This person signs in through a connected app, which holds their password."
            )
        ensure_only_here(user, request.user.active_membership.organization)

        password = issue_temporary_password(user)
        record_event("staff.password_reset", actor=request.user, target=membership)
        return Response({"temporary_password": password}, headers={"Cache-Control": "no-store"})


class StaffInviteView(APIView):
    """Sends a fresh invitation link, which ends any earlier one."""

    permission_classes = [IsAuthenticated, require_permission("staff.manage")]

    @extend_schema(
        request=None, responses={200: InvitationLinkSerializer, 400: ErrorResponseSerializer}
    )
    def post(self, request, pk):
        membership = get_object_or_404(_staff_queryset(), pk=pk)
        link = invitations.invite(membership, actor=request.user)
        return Response({"invite_link": link}, headers={"Cache-Control": "no-store"})


class PublicInvitationView(APIView):
    """What an invitation link is for, before the person chooses a password."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def _invitation(self, organization_slug, token):
        organization = Organization.objects.filter(slug=organization_slug, is_active=True).first()
        if organization is None:
            raise exceptions.NotFound(invitations.NOT_VALID)
        return organization

    @extend_schema(
        auth=[],
        parameters=[
            OpenApiParameter("organization", str, required=True),
            OpenApiParameter("token", str, required=True),
        ],
        responses={200: InvitationSerializer, 404: ErrorResponseSerializer},
    )
    def get(self, request):
        organization = self._invitation(request.query_params.get("organization"), "")
        with organization_context(organization.id):
            invitation = invitations.open_invitation(request.query_params.get("token", ""))
            user = invitation.membership.user
            return Response(
                {
                    "email": user.email,
                    "full_name": user.full_name,
                    "organization": organization.name,
                }
            )

    @extend_schema(
        auth=[],
        request=AcceptInvitationSerializer,
        responses={204: None, 400: ErrorResponseSerializer, 404: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = self._invitation(data["organization"], data["token"])
        with organization_context(organization.id):
            invitations.accept(
                data["token"], password=data["password"], full_name=data["full_name"]
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffMfaResetView(APIView):
    """For a lost authenticator. Their next login starts MFA setup again."""

    permission_classes = [IsAuthenticated, require_permission("staff.manage")]

    @extend_schema(request=None, responses={204: None, 403: ErrorResponseSerializer})
    def post(self, request, pk):
        membership = get_object_or_404(Membership, pk=pk)
        if membership.user_id == request.user.pk:
            raise exceptions.PermissionDenied("You cannot reset your own MFA.")
        reset_mfa(membership.user)
        record_event("mfa.reset", actor=request.user, target=membership)
        return Response(status=status.HTTP_204_NO_CONTENT)
