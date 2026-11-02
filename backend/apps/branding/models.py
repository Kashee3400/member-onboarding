from django.core.validators import RegexValidator
from django.db import models

from apps.organizations.models import OrganizationOwnedModel

DEFAULT_PRIMARY = "#0284C7"
DEFAULT_ACCENT = "#F59E0B"

hex_color = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a colour like #0284C7.")


class Branding(OrganizationOwnedModel):
    """How the portal looks for one organization. All of this is public by design."""

    display_name = models.CharField(max_length=200, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    primary_color = models.CharField(max_length=7, default=DEFAULT_PRIMARY, validators=[hex_color])
    accent_color = models.CharField(max_length=7, default=DEFAULT_ACCENT, validators=[hex_color])
    logo_path = models.CharField(max_length=300, blank=True)
    login_image_path = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "organization_branding"
        constraints = [
            models.UniqueConstraint(fields=["organization"], name="unique_branding_per_org"),
        ]

    def __str__(self):
        return self.display_name or str(self.organization_id)
