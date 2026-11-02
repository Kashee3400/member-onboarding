from datetime import datetime

from rest_framework import serializers

from apps.applications.models import Status

from .models import BatchStatus, PdfBatch
from .tasks import KEEP_FOR


class ReportFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Status.choices, required=False)
    mpp = serializers.UUIDField(required=False)
    mcc = serializers.UUIDField(required=False)
    route = serializers.UUIDField(required=False)
    submitted_from = serializers.DateField(required=False)
    submitted_to = serializers.DateField(required=False)


class ReportSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    by_status = serializers.DictField(child=serializers.IntegerField())


class PrintFilterSerializer(serializers.Serializer):
    """Which approved members to print: by the day of final approval, place or person."""

    approved_from = serializers.DateField(required=False)
    approved_to = serializers.DateField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)
    mcc = serializers.UUIDField(required=False)
    bmc = serializers.UUIDField(required=False)
    route = serializers.UUIDField(required=False)
    mpp = serializers.UUIDField(required=False)

    def validate(self, attrs):
        start, end = attrs.get("approved_from"), attrs.get("approved_to")
        if start and end and start > end:
            raise serializers.ValidationError({"approved_to": ["The end is before the start."]})
        return attrs


class PdfJobRequestSerializer(PrintFilterSerializer):
    variant = serializers.ChoiceField(choices=["full", "single"])
    want_zip = serializers.BooleanField(default=True)
    want_merged = serializers.BooleanField(default=False)
    # Forms taken off the preview by hand.
    exclude = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=2000)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs["want_zip"] and not attrs["want_merged"]:
            raise serializers.ValidationError({"detail": ["Choose a ZIP, a print file, or both."]})
        return attrs


class PrintPreviewRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    form_number = serializers.CharField()
    full_name = serializers.CharField()
    tr_code = serializers.CharField()
    mpp = serializers.CharField()
    approved_at = serializers.DateTimeField()


class PrintPreviewSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    ready = serializers.IntegerField(help_text="Forms already made once, which take no time.")
    estimated_seconds = serializers.IntegerField()
    estimated_bytes = serializers.IntegerField()
    rows = PrintPreviewRowSerializer(many=True)


class MergedPartSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    name = serializers.CharField()
    forms = serializers.IntegerField()
    bytes = serializers.IntegerField()


class PdfBatchSerializer(serializers.ModelSerializer):
    failed_count = serializers.SerializerMethodField()
    merged_parts = serializers.SerializerMethodField()
    queue_position = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()

    class Meta:
        model = PdfBatch
        fields = [
            "id",
            "status",
            "variant",
            "want_zip",
            "want_merged",
            "label",
            "form_count",
            "phase",
            "cursor",
            "processed",
            "failed_count",
            "failed_forms",
            "current_form",
            "merged_parts",
            "error",
            "queue_position",
            "started_at",
            "finished_at",
            "expires_at",
            "requested_by_name",
            "created_at",
        ]

    @staticmethod
    def get_failed_count(batch) -> int:
        return len(batch.failed_forms)

    @staticmethod
    def get_merged_parts(batch) -> list[dict]:
        return [
            {
                "index": index,
                "name": part.get("name", ""),
                "forms": part["forms"],
                "bytes": part["bytes"],
            }
            for index, part in enumerate(batch.merged_parts)
        ]

    @staticmethod
    def get_queue_position(batch) -> int | None:
        """1 when it is next in line. Null once it has started."""
        if batch.status != BatchStatus.QUEUED:
            return None
        ahead = PdfBatch.objects.filter(
            status__in=[BatchStatus.QUEUED, BatchStatus.RUNNING], created_at__lt=batch.created_at
        ).count()
        return ahead + 1

    @staticmethod
    def get_expires_at(batch) -> datetime | None:
        return batch.finished_at + KEEP_FOR if batch.finished_at else None
