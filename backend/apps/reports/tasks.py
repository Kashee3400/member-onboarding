"""
PDF jobs run one at a time per organization, a few forms per task, so printing a
month of members never holds up approvals. Each form is its own short transaction:
whoever watches the job sees every form as it is made.
"""

import uuid
from datetime import timedelta
from io import BytesIO

import structlog
from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from apps.applications.models import Application, Status
from apps.applications.services import printed_form
from apps.core.tenancy import organization_context
from apps.documents import storage
from apps.notifications.services import notify
from apps.organizations.models import Membership

from .models import BatchPhase, BatchStatus, PdfBatch

logger = structlog.get_logger(__name__)

# Forms per task. Small enough that a cancel takes effect within a minute.
CHUNK = 25
# A print file stops growing at this size, so it still opens on an office computer.
MERGED_PART_BYTES = 150 * 1024 * 1024
# Finished jobs keep their print files this long. They hold Aadhaar card images.
KEEP_FOR = timedelta(days=7)


def _export_path(organization_id) -> str:
    now = timezone.localtime()
    return f"{organization_id}/exports/{now:%Y}/{now:%m}/{uuid.uuid4().hex}.enc"


def _forget_old_files() -> None:
    old = PdfBatch.objects.filter(finished_at__lt=timezone.now() - KEEP_FOR).exclude(
        merged_parts=[]
    )
    for batch in old:
        for part in batch.merged_parts:
            storage.delete_quietly(part["path"])
        batch.merged_parts = []
        batch.save(update_fields=["merged_parts", "updated_at"])


def start_next(organization_id) -> None:
    """Starts the oldest waiting job, unless one is already running."""
    with organization_context(organization_id):
        with connection.cursor() as cursor:
            # Two requests at once must not both start a job.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"pdf:{organization_id}"])
        if PdfBatch.objects.filter(status=BatchStatus.RUNNING).exists():
            return
        _forget_old_files()
        batch = PdfBatch.objects.filter(status=BatchStatus.QUEUED).order_by("created_at").first()
        if batch is None:
            return
        batch.status = BatchStatus.RUNNING
        batch.started_at = timezone.now()
        batch.save(update_fields=["status", "started_at", "updated_at"])
        transaction.on_commit(lambda: run_pdf_batch.delay(str(batch.id), str(organization_id)))


def _still_running(batch_id) -> bool:
    return PdfBatch.objects.filter(pk=batch_id, status=BatchStatus.RUNNING).exists()


def _render_chunk(batch_id, organization_id) -> bool:
    """Makes the next few forms. True when there is more to do."""
    with organization_context(organization_id):
        batch = PdfBatch.objects.get(pk=batch_id)
        ids = batch.application_ids[batch.cursor : batch.cursor + CHUNK]
        variant = batch.variant

    for application_id in ids:
        with organization_context(organization_id):
            if not _still_running(batch_id):
                return False
            batch = PdfBatch.objects.select_for_update().get(pk=batch_id)
            application = (
                Application.objects.filter(pk=application_id, status=Status.APPROVED)
                .select_related("mpp__mcc", "member")
                .first()
            )
            batch.cursor += 1
            batch.current_form = application.form_number if application else ""
            try:
                if application is None:
                    raise LookupError("no longer approved")
                with transaction.atomic():
                    printed_form(application, variant)
                batch.processed += 1
            except Exception:
                logger.exception("pdf_form_failed", batch=batch_id, application=application_id)
                batch.failed_forms = [
                    *batch.failed_forms,
                    application.form_number if application else application_id,
                ]
            batch.save(
                update_fields=["cursor", "current_form", "processed", "failed_forms", "updated_at"]
            )

    with organization_context(organization_id):
        batch = PdfBatch.objects.get(pk=batch_id)
        if batch.cursor < batch.form_count:
            return True
        if batch.want_merged and batch.processed:
            batch.phase = BatchPhase.MERGE
            batch.cursor = 0
            batch.current_form = ""
            batch.save(update_fields=["phase", "cursor", "current_form", "updated_at"])
            return True
        return False


def _merge_part(batch_id, organization_id) -> bool:
    """Joins forms into one print file of up to MERGED_PART_BYTES. True when more remain."""
    with organization_context(organization_id):
        batch = PdfBatch.objects.get(pk=batch_id)
        failed = set(batch.failed_forms)
        ids = batch.application_ids
        writer = PdfWriter()
        size = forms = 0
        first = last = ""
        cursor = batch.cursor
        while cursor < len(ids) and size < MERGED_PART_BYTES:
            application = Application.objects.filter(pk=ids[cursor]).first()
            cursor += 1
            if application is None or application.form_number in failed:
                continue
            content = printed_form(application, batch.variant)
            for page in PdfReader(BytesIO(content)).pages:
                writer.add_page(page)
            size += len(content)
            forms += 1
            first = first or application.form_number
            last = application.form_number

        batch = PdfBatch.objects.select_for_update().get(pk=batch_id)
        if batch.status != BatchStatus.RUNNING:
            return False
        if forms:
            output = BytesIO()
            writer.write(output)
            path = _export_path(organization_id)
            storage.write(path, output.getvalue(), upload=False)
            name = first if first == last else f"{first}-{last}"
            batch.merged_parts = [
                *batch.merged_parts,
                {"path": path, "name": name, "forms": forms, "bytes": output.tell()},
            ]
        batch.cursor = cursor
        batch.current_form = last
        batch.save(update_fields=["merged_parts", "cursor", "current_form", "updated_at"])
        return cursor < len(ids)


def _finish(batch_id, organization_id, status, error="") -> None:
    with organization_context(organization_id):
        batch = PdfBatch.objects.select_for_update().get(pk=batch_id)
        if batch.status == BatchStatus.RUNNING:
            batch.status = status
            batch.error = error[:300]
        batch.finished_at = batch.finished_at or timezone.now()
        batch.current_form = ""
        batch.save(update_fields=["status", "error", "finished_at", "current_form", "updated_at"])
        if batch.status == BatchStatus.DONE:
            recipient = Membership.objects.filter(user_id=batch.requested_by_id).first()
            failed = len(batch.failed_forms)
            notify(
                [recipient] if recipient else [],
                title="Your PDFs are ready",
                body=f"{batch.processed} forms are ready to download"
                + (f", {failed} could not be made." if failed else "."),
            )
    start_next(organization_id)


@shared_task
def run_pdf_batch(batch_id: str, organization_id: str) -> None:
    with organization_context(organization_id):
        batch = PdfBatch.objects.filter(pk=batch_id).first()
        if batch is None:
            return
        phase, running = batch.phase, batch.status == BatchStatus.RUNNING
    if not running:
        # Cancelled in the meantime: the next job in line gets its turn.
        start_next(organization_id)
        return
    try:
        more = (
            _merge_part(batch_id, organization_id)
            if phase == BatchPhase.MERGE
            else _render_chunk(batch_id, organization_id)
        )
    except Exception as error:
        # The person waiting sees a failure, instead of a job running forever.
        logger.exception("pdf_batch_failed", batch=batch_id)
        _finish(batch_id, organization_id, BatchStatus.FAILED, str(error))
        return
    if more:
        run_pdf_batch.delay(batch_id, organization_id)
        return
    with organization_context(organization_id):
        made = PdfBatch.objects.get(pk=batch_id).processed
    if made:
        _finish(batch_id, organization_id, BatchStatus.DONE)
    else:
        _finish(batch_id, organization_id, BatchStatus.FAILED, "No form could be made.")
