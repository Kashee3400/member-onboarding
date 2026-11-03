"""
Everything held about one member's form, for a member asking for their data or a
legal request. The archive is decrypted, so making one is its own permission and
is always audited.

    record.json    the form, both numbers in full, decisions, step approvals, payment
    history.json   every audited event on the form, oldest first, with who did it
    documents/     the current photos, as uploaded
    forms/         the printed forms, once approved
"""

import io
import json
import mimetypes
import zipfile

from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.documents import storage

from . import services


def _record(application) -> dict:
    try:
        member = application.member
        joined = {"tr_code": member.tr_code, "joined_at": member.joined_at}
    except ObjectDoesNotExist:
        joined = None
    return {
        "form_number": application.form_number,
        "status": application.status,
        "revision": application.revision,
        "created_at": application.created_at,
        "submitted_at": application.submitted_at,
        "mobile_verified_at": application.mobile_verified_at,
        "email_verified_at": application.email_verified_at,
        "mpp": {"code": application.mpp.code, "name": application.mpp.name},
        "member": joined,
        "form": application.data,
        "numbers": services.numbers_of(application),
        "payment": application.payment,
        "decisions": [
            {
                "stage": decision.stage,
                "decision": decision.decision,
                "reason": decision.reason,
                "revision": decision.revision,
                "by": decision.decided_by_name,
                "at": decision.decided_at,
            }
            for decision in application.decisions.order_by("decided_at")
        ],
        "step_approvals": [
            {
                "step": approval.step,
                "revision": approval.revision,
                "by": approval.decided_by_name,
                "at": approval.decided_at,
            }
            for approval in application.step_approvals.order_by("decided_at")
        ],
    }


def _history(application) -> list[dict]:
    events = list(AuditEvent.objects.filter(target_id=str(application.pk)).order_by("occurred_at"))
    names = {
        user.pk: user.full_name or user.email
        for user in User.objects.filter(pk__in={event.actor_id for event in events})
    }
    return [
        {
            "at": event.occurred_at,
            "action": event.action,
            "by": names.get(event.actor_id, ""),
            "details": event.metadata,
        }
        for event in events
    ]


def member_data_archive(application, *, user) -> bytes:
    record_event("application.data_exported", actor=user, target=application)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "record.json",
            json.dumps(_record(application), cls=DjangoJSONEncoder, indent=2, ensure_ascii=False),
        )
        # The export itself is in the history, as the last entry.
        archive.writestr(
            "history.json",
            json.dumps(_history(application), cls=DjangoJSONEncoder, indent=2, ensure_ascii=False),
        )
        for document in application.documents.filter(is_current=True).order_by("document_type"):
            extension = mimetypes.guess_extension(document.content_type) or ".bin"
            archive.writestr(
                f"documents/{document.document_type}{extension}",
                storage.read(document.relative_path),
            )
        for pdf in application.pdfs.order_by("variant"):
            archive.writestr(f"forms/{pdf.variant}.pdf", storage.read(pdf.relative_path))
    return buffer.getvalue()
