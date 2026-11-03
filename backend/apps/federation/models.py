from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel
from apps.organizations.models import Membership, Organization, OrganizationOwnedModel


class TrustedIssuer(UUIDModel, TimeStampedModel):
    """
    A host application allowed to vouch for its own users.

    Not row-level isolated: an incoming assertion names its issuer before any
    organization is known. The API filters by organization explicitly.

    Several organizations may trust the same host, as when one ERP serves more than
    one company: each registers it in its own Connected Apps, and a sign-in goes to
    the organization that owns the person's MPPs (services.verify_assertion).
    """

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=100)
    issuer = models.CharField(max_length=200)
    audience = models.CharField(max_length=200)
    public_key = models.TextField(help_text="RSA public key in PEM format.")
    default_role_code = models.SlugField(
        max_length=60, blank=True, help_text="Role given on first sign-in. Blank grants nothing."
    )
    syncs_mpp_assignments = models.BooleanField(
        default=False, help_text="Treat the host's MPP list as the source of truth."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "federation_trusted_issuer"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "issuer"], name="unique_issuer_per_organization"
            ),
        ]

    def __str__(self):
        return self.name


class ExternalIdentity(OrganizationOwnedModel):
    """Links a host application's user to a local one. Never matched by email."""

    issuer = models.ForeignKey(TrustedIssuer, on_delete=models.PROTECT, related_name="identities")
    subject = models.CharField(max_length=200)
    membership = models.OneToOneField(
        Membership, on_delete=models.PROTECT, related_name="external_identity"
    )

    class Meta:
        db_table = "federation_external_identity"
        constraints = [
            models.UniqueConstraint(fields=["issuer", "subject"], name="unique_subject_per_issuer"),
        ]

    def __str__(self):
        return f"{self.subject} @ {self.issuer_id}"
