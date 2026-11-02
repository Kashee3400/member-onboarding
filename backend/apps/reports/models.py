from django.conf import settings
from django.db import models

from apps.organizations.models import OrganizationOwnedModel


class BatchStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class BatchPhase(models.TextChoices):
    RENDER = "render", "Making forms"
    MERGE = "merge", "Joining into files for print"


class PdfBatch(OrganizationOwnedModel):
    """
    Printed forms of many approved members, made in the background a few at a time.
    Each form's PDF is stored once on its own, so the ZIP is streamed from those
    when downloaded and only the merged print files are kept here.
    """

    status = models.CharField(
        max_length=10, choices=BatchStatus.choices, default=BatchStatus.QUEUED
    )
    variant = models.CharField(max_length=10, default="full")
    want_zip = models.BooleanField(default=True)
    want_merged = models.BooleanField(default=False)
    # What was asked for, in words, for the list of jobs.
    label = models.CharField(max_length=300, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    form_count = models.PositiveIntegerField(default=0)

    phase = models.CharField(max_length=10, choices=BatchPhase.choices, default=BatchPhase.RENDER)
    cursor = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    failed_forms = models.JSONField(default=list, blank=True)
    current_form = models.CharField(max_length=20, blank=True)
    merged_parts = models.JSONField(default=list, blank=True)
    error = models.CharField(max_length=300, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    requested_by_name = models.CharField(max_length=200)

    class Meta:
        db_table = "report_pdf_batch"

    def __str__(self):
        return f"{self.status}: {self.form_count} forms"

    @property
    def application_ids(self) -> list[str]:
        return self.filters.get("application_ids", [])
