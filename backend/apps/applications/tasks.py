import structlog
from celery import shared_task

from apps.core.tenancy import organization_context

from . import retention, services
from .models import Application
from .pdf.render import VARIANTS

logger = structlog.get_logger(__name__)

# Tries after the first, waiting a little longer each time.
PRINT_RETRIES = 3


@shared_task(bind=True, max_retries=PRINT_RETRIES)
def make_printed_forms(self, application_id: str, organization_id: str) -> None:
    """
    Makes and stores both variants once a form is approved, so printing many forms
    later reads stored copies. A failure only means the first download renders it.
    """
    try:
        with organization_context(organization_id):
            application = Application.objects.select_related("mpp").get(pk=application_id)
            for variant in VARIANTS:
                services.printed_form(application, variant)
    except Exception as error:
        if self.request.retries >= PRINT_RETRIES:
            logger.exception("printed_form_failed", application=application_id)
            return
        logger.warning("printed_form_retry", application=application_id, error=str(error))
        raise self.retry(exc=error, countdown=60 * 2**self.request.retries) from error


@shared_task
def discard_stale_drafts() -> int:
    """Nightly, for every organization: drafts past their retention period go."""
    from apps.organizations.models import Organization

    total = 0
    for organization_id in Organization.objects.values_list("id", flat=True):
        with organization_context(organization_id):
            total += retention.discard_stale_drafts()
    if total:
        logger.info("stale_drafts_discarded", count=total)
    return total


@shared_task
def read_aadhaar_qr(application_id: str, organization_id: str, document_id: str) -> None:
    """Reads the QR from an uploaded Aadhaar photo. A failure only means none was read."""
    from apps.documents import storage
    from apps.documents.models import Document

    from . import aadhaar_check

    try:
        with organization_context(organization_id):
            document = Document.objects.get(pk=document_id)
            application = Application.objects.get(pk=application_id)
            aadhaar_check.read_from_photo(
                application, storage.read(document.relative_path), user=document.uploaded_by
            )
    except Exception:
        logger.exception("aadhaar_qr_from_photo_failed", application=application_id)
