"""
Drafts are not kept for ever. A form a facilitator started and never submitted
holds a person's Aadhaar and bank photos for no purpose, so after the
organization's retention period it is discarded and its photos are deleted.
Submitted forms, members and the audit log are never touched here.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_event
from apps.documents import storage
from apps.documents.models import Document

from .models import Application, OrganizationProfile, Status


def retention_days() -> int:
    profile = OrganizationProfile.objects.first()
    return profile.draft_retention_days if profile else OrganizationProfile.DEFAULT_DRAFT_RETENTION


def discard_stale_drafts(now=None) -> int:
    """Runs inside one organization. Returns how many drafts went."""
    days = retention_days()
    if not days:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    stale = Application.objects.filter(status=Status.DRAFT, revision=0, updated_at__lt=cutoff)
    count = 0
    for application in stale:
        with transaction.atomic():
            documents = list(Document.objects.filter(application=application))
            Document.objects.filter(application=application).delete()
            application.status = Status.DISCARDED
            application.save(update_fields=["status", "updated_at"])
            record_event(
                "application.discarded",
                target=application,
                metadata={"reason": "retention", "after_days": days, "documents": len(documents)},
            )
            # Files go only once the database agrees.
            paths = [document.relative_path for document in documents]
            transaction.on_commit(lambda paths=paths: [storage.delete_quietly(p) for p in paths])
        count += 1
    return count
