from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.organizations.models import Membership, OrganizationOwnedModel


class Plant(OrganizationOwnedModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "hierarchy_plant"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="unique_plant_code_per_organization"
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class Mcc(OrganizationOwnedModel):
    """A milk collection centre, under a plant."""

    plant = models.ForeignKey(Plant, on_delete=models.PROTECT, related_name="mccs")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "hierarchy_mcc"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="unique_mcc_code_per_organization"
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class Bmc(OrganizationOwnedModel):
    """A bulk milk cooler, under an MCC."""

    mcc = models.ForeignKey(Mcc, on_delete=models.PROTECT, related_name="bmcs")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "hierarchy_bmc"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="unique_bmc_code_per_organization"
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class Route(OrganizationOwnedModel):
    """A collection route, under a BMC."""

    bmc = models.ForeignKey(Bmc, on_delete=models.PROTECT, related_name="routes")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "hierarchy_route"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="unique_route_code_per_organization"
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class Mpp(OrganizationOwnedModel):
    """
    A collection point, which owns its applications. It sits in one hamlet, and a
    village can have several MPPs in different hamlets.
    """

    mcc = models.ForeignKey(Mcc, on_delete=models.PROTECT, related_name="mpps")
    route = models.ForeignKey(
        Route, on_delete=models.PROTECT, null=True, blank=True, related_name="mpps"
    )
    code = models.CharField(max_length=30, help_text="Shown to people everywhere.")
    source_code = models.CharField(
        max_length=30, blank=True, help_text="Internal code in the source ERP, for matching only."
    )
    name = models.CharField(max_length=150)
    village_name = models.CharField(max_length=150, blank=True)
    state_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="First two digits of a member code. Blank uses the organization's default.",
    )
    hamlet_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="Two digits after the village, as a village can have several MPPs.",
    )
    village_code = models.CharField(
        max_length=8, validators=[RegexValidator(r"^\d{8}$", "Must be 8 digits.")]
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "hierarchy_mpp"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="unique_mpp_code_per_organization"
            ),
            models.UniqueConstraint(
                fields=["organization", "village_code", "hamlet_code"],
                name="unique_mpp_per_village_hamlet",
            ),
            models.UniqueConstraint(
                fields=["organization", "source_code"],
                condition=~Q(source_code=""),
                name="unique_mpp_source_code",
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class Responsibility(models.TextChoices):
    FACILITATOR = "facilitator", "Facilitator"
    AREA_MANAGER = "area_manager", "Area Manager"


class MccAssignment(OrganizationOwnedModel):
    """
    Someone who approves forms for an MCC, and so for every MPP under it: an Area
    Manager, or one of a CS or Finance team. An MCC can have several, and one person
    several MCCs. An MPP moved to another MCC moves to that MCC's people at once.
    """

    mcc = models.ForeignKey(Mcc, on_delete=models.PROTECT, related_name="assignments")
    membership = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="mcc_assignments"
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "hierarchy_mcc_assignment"
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["mcc", "membership"],
                condition=Q(ended_at__isnull=True),
                name="unique_active_mcc_assignment",
            ),
        ]

    def __str__(self):
        return f"{self.mcc_id} -> {self.membership_id}"


class MccCover(OrganizationOwnedModel):
    """
    One person works another's MCCs for a few days, say during leave. It follows
    whatever MCCs the absent person holds, keeps theirs untouched, and stops on its
    own after the last day, as access checks the dates rather than waiting for a job.
    """

    absent = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="covers_needed")
    colleague = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="covers_given")
    starts_on = models.DateField()
    ends_on = models.DateField()
    reason = models.CharField(max_length=300)
    given_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "hierarchy_mcc_cover"
        ordering = ["-starts_on", "-created_at"]
        indexes = [
            models.Index(fields=["colleague", "ends_on"], name="mcc_cover_colleague_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__gte=F("starts_on")), name="mcc_cover_ends_after_it_starts"
            ),
            models.CheckConstraint(
                condition=~Q(absent=F("colleague")), name="mcc_cover_not_oneself"
            ),
        ]

    def __str__(self):
        return f"{self.colleague_id} covers {self.absent_id}"


class MppAssignment(OrganizationOwnedModel):
    """
    Who is responsible for an MPP, and when. Rows are closed, never rewritten, so
    the full handover history survives. Access always follows the open row.
    """

    mpp = models.ForeignKey(Mpp, on_delete=models.PROTECT, related_name="assignments")
    membership = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="mpp_assignments"
    )
    responsibility = models.CharField(max_length=20, choices=Responsibility.choices)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "hierarchy_mpp_assignment"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["membership", "ended_at"], name="assignment_member_active_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["mpp", "responsibility"],
                condition=Q(ended_at__isnull=True),
                name="unique_active_assignment_per_mpp",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("started_at")),
                name="assignment_ends_after_it_starts",
            ),
        ]

    def __str__(self):
        return f"{self.responsibility}: {self.membership_id} @ {self.mpp_id}"
