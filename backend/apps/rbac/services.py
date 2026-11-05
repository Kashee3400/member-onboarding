from rest_framework.exceptions import PermissionDenied, ValidationError

from .catalog import PERMISSIONS, SYSTEM_ROLES
from .models import MembershipRole, Role

ROLE_MANAGEMENT_PERMISSION = "roles.manage"


def permissions_for(membership) -> frozenset[str]:
    rows = Role.objects.filter(member_links__membership=membership).values_list(
        "permissions", flat=True
    )
    return frozenset(code for permissions in rows for code in permissions)


def requires_mfa(membership) -> bool:
    return Role.objects.filter(member_links__membership=membership, requires_mfa=True).exists()


def role_codes_for(membership) -> set[str]:
    return set(
        Role.objects.filter(member_links__membership=membership).values_list("code", flat=True)
    )


def role_names_for(membership) -> set[str]:
    return set(
        Role.objects.filter(member_links__membership=membership).values_list("name", flat=True)
    )


def sync_system_roles() -> None:
    """
    Bring the active organization's standard roles in line with the catalog. One the
    organization has changed keeps its permissions, less any the catalog dropped.
    """
    for code, definition in SYSTEM_ROLES.items():
        role = Role.objects.filter(code=code).first()
        if role is not None and role.customized:
            kept = sorted(set(role.permissions) & set(PERMISSIONS))
            if kept != role.permissions:
                role.permissions = kept
                role.save(update_fields=["permissions", "updated_at"])
            continue
        Role.objects.update_or_create(
            code=code,
            defaults={
                "name": definition["name"],
                "is_system": True,
                "customized": False,
                "requires_mfa": definition.get("requires_mfa", False),
                "permissions": sorted(definition["permissions"]),
            },
        )


def reset_system_role(role) -> None:
    """Back to the standard permissions, and followed by deployments again."""
    definition = SYSTEM_ROLES[role.code]
    role.customized = False
    role.requires_mfa = definition.get("requires_mfa", False)
    role.permissions = sorted(definition["permissions"])
    role.save(update_fields=["customized", "requires_mfa", "permissions", "updated_at"])


def grant_role(membership, role_code: str) -> None:
    MembershipRole.objects.get_or_create(
        membership=membership, role=Role.objects.get(code=role_code)
    )


def ensure_can_grant(actor_permissions, permissions) -> None:
    """Nobody may hand out more than they hold, or role management becomes escalation."""
    excess = set(permissions) - set(actor_permissions)
    if excess:
        raise PermissionDenied(f"You cannot grant: {', '.join(sorted(excess))}")


def ensure_can_assign(actor, roles, *, membership=None) -> None:
    """
    Admins hold no approval rights, yet must appoint approvers, so system roles
    can be given to others. Nobody can raise their own access, and custom roles
    stay limited to what the actor holds.
    """
    assigning_self = membership is not None and membership.user_id == actor.pk
    for role in roles:
        if assigning_self or not role.is_system:
            ensure_can_grant(actor.active_permissions, role.permissions)


def set_membership_roles(membership, roles) -> None:
    wanted = {role.id: role for role in roles}
    existing = set(membership.role_links.values_list("role_id", flat=True))

    membership.role_links.exclude(role_id__in=wanted).delete()
    MembershipRole.objects.bulk_create(
        MembershipRole(organization_id=membership.organization_id, membership=membership, role=role)
        for role_id, role in wanted.items()
        if role_id not in existing
    )


def ensure_role_manager_remains() -> None:
    """Call after any change that could remove the organization's last role manager."""
    managing_roles = list(
        Role.objects.select_for_update().filter(permissions__contains=[ROLE_MANAGEMENT_PERMISSION])
    )
    still_managed = MembershipRole.objects.filter(
        role__in=managing_roles, membership__is_active=True
    ).exists()
    if not still_managed:
        raise ValidationError(
            {"detail": ["This change would leave the organization without a role manager."]}
        )
