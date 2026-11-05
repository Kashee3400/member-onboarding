from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.organizations.models import Membership, OrganizationOwnedModel


class Role(OrganizationOwnedModel):
    """A named set of permissions. System roles are kept in step with the catalog."""

    code = models.SlugField(max_length=60)
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    # A standard role this organization has changed: deployments then leave it as it is.
    customized = models.BooleanField(default=False)
    requires_mfa = models.BooleanField(default=False)
    permissions = ArrayField(models.CharField(max_length=60), default=list, blank=True)

    class Meta:
        db_table = "rbac_role"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="unique_role_code_per_organization"
            ),
        ]

    def __str__(self):
        return self.name


class MembershipRole(OrganizationOwnedModel):
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="role_links")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="member_links")

    class Meta:
        db_table = "rbac_membership_role"
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "role"], name="unique_role_per_membership"
            ),
        ]

    def __str__(self):
        return f"{self.membership_id} -> {self.role_id}"


class StaffInvitation(OrganizationOwnedModel):
    """
    A link that lets someone set their own password. Only a hash of its token is
    kept, it works once, and a newer one or a revoke ends it.
    """

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="invitations")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "rbac_staff_invitation"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.membership_id} until {self.expires_at:%Y-%m-%d}"
