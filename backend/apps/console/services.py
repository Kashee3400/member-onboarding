from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import exceptions

from apps.audit.services import record_event
from apps.branding.models import Branding
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership, Organization
from apps.rbac import invitations
from apps.rbac.services import grant_role, sync_system_roles


@transaction.atomic
def create_organization(*, name, slug, admin_email, admin_name, email_domain, actor) -> dict:
    """
    A new organization with the standard roles and its first admin. The admin gets
    an invitation link to choose a password; it is returned too, because a brand new
    organization has no mail set up to send it with.
    """
    if Organization.objects.filter(slug=slug).exists():
        raise exceptions.ValidationError({"slug": ["Another organization uses this short name."]})
    if email_domain and not admin_email.endswith(f"@{email_domain}"):
        raise exceptions.ValidationError(
            {"admin_email": [f"The first admin needs an @{email_domain} address too."]}
        )

    organization = Organization.objects.create(name=name, slug=slug)
    User = get_user_model()
    user = User.objects.filter(email__iexact=admin_email).first()
    if user is None:
        user = User.objects.create_user(admin_email, None, full_name=admin_name)

    with organization_context(organization.id):
        sync_system_roles()
        Branding.objects.create(display_name=name, email_domain=email_domain)
        membership = Membership.objects.create(organization=organization, user=user)
        grant_role(membership, "org_admin")
        record_event(
            "organization.created", actor=actor, target=organization, metadata={"by": "console"}
        )
        # Someone already working in another organization signs in with their password.
        link = (
            invitations.invite(membership, actor=actor)
            if invitations.is_pending(membership)
            else None
        )
    return {"organization": organization, "invitation_link": link}


def set_active(organization, active: bool, *, actor, own_organization_id) -> Organization:
    if not active and organization.id == own_organization_id:
        raise exceptions.ValidationError(
            {"is_active": ["You cannot switch off the organization you are signed in to."]}
        )
    organization.is_active = active
    organization.save(update_fields=["is_active", "updated_at"])
    with organization_context(organization.id):
        record_event(
            "organization.enabled" if active else "organization.disabled",
            actor=actor,
            target=organization,
        )
    return organization
