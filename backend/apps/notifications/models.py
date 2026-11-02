from django.db import models

from apps.organizations.models import Membership, OrganizationOwnedModel


class Notification(OrganizationOwnedModel):
    """Always shown in the portal. Email is a copy, sent when mail is configured."""

    recipient = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    application = models.ForeignKey(
        "applications.Application",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification"
        indexes = [
            models.Index(fields=["recipient", "read_at"], name="notification_unread_idx"),
        ]

    def __str__(self):
        return self.title


class Preference(OrganizationOwnedModel):
    """What a person wants to hear about. No row means the defaults."""

    membership = models.OneToOneField(
        Membership, on_delete=models.CASCADE, related_name="notification_preference"
    )
    morning_summary = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_preference"

    def __str__(self):
        return f"{self.membership_id}"


class MorningSummary(OrganizationOwnedModel):
    """One row per person per day, so a second run the same morning sends nothing."""

    recipient = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="morning_summaries"
    )
    day = models.DateField()
    waiting = models.PositiveIntegerField()
    overdue = models.PositiveIntegerField()

    class Meta:
        db_table = "notification_morning_summary"
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "day"], name="unique_morning_summary_per_day"
            ),
        ]

    def __str__(self):
        return f"{self.recipient_id} {self.day}"
