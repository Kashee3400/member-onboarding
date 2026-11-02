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
