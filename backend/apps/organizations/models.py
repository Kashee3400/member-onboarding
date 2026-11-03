from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel
from apps.core.tenancy import get_current_organization_id


class Organization(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=60, unique=True)
    is_active = models.BooleanField(default=True)
    storage_limit_mb = models.PositiveIntegerField(
        null=True, blank=True, help_text="Uploads stop once files reach this. Blank: no limit."
    )

    class Meta:
        db_table = "organization"

    def __str__(self):
        return self.name


class OrganizationOwnedModel(UUIDModel, TimeStampedModel):
    """
    Base for data belonging to one organization.

    Every concrete subclass needs `enable_rls(<table>)` in its migration.
    tests/test_tenancy.py fails if one is missing.
    """

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.organization_id is None:
            organization_id = get_current_organization_id()
            if organization_id is None:
                raise ImproperlyConfigured("No active organization for this write.")
            self.organization_id = organization_id
        super().save(*args, **kwargs)


class Membership(OrganizationOwnedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    is_active = models.BooleanField(default=True)
    photo_path = models.CharField(max_length=300, blank=True)
    # For signing in to the standalone app with a code by SMS.
    mobile = models.CharField(max_length=10, blank=True)

    class Meta:
        db_table = "organization_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="unique_membership_per_organization"
            ),
            models.UniqueConstraint(
                fields=["organization", "mobile"],
                condition=~models.Q(mobile=""),
                name="unique_staff_mobile_per_organization",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.organization_id}"

    @property
    def photo_url(self) -> str | None:
        if not self.photo_path:
            return None
        # The name changes with each upload, so browsers can cache a photo for a long time.
        version = PurePosixPath(self.photo_path).stem
        return f"/api/v1/staff/{self.pk}/photo/?v={version}"
