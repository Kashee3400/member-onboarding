from django.conf import settings
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


class ContactOtp(OrganizationOwnedModel):
    """
    One code sent to a member's mobile number or email, to prove the form has it right.
    Only a hash of the code is kept, and the number or address it went to, so a code
    sent to an old number proves nothing about a new one.
    """

    class Channel(models.TextChoices):
        MOBILE = "mobile", "Mobile"
        EMAIL = "email", "Email"

    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="contact_otps"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    sent_to = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    tries = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "notification_contact_otp"
        indexes = [
            models.Index(
                fields=["application", "channel", "created_at"], name="contact_otp_lookup_idx"
            )
        ]

    def __str__(self):
        return f"{self.application_id} {self.channel}"
