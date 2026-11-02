from django.db import transaction

from apps.audit.services import record_event

from . import images, storage
from .models import REQUIRED_DOCUMENTS, SIGNATURE_DOCUMENTS, Document, StaffSignature


def attach_document(application, *, document_type, raw, user, user_name) -> Document:
    content, content_type = images.normalize_document(raw)
    path = storage.application_file_path(application, document_type)
    storage.write(path, content)

    try:
        with transaction.atomic():
            Document.objects.filter(
                application=application, document_type=document_type, is_current=True
            ).update(is_current=False)
            document = Document.objects.create(
                application=application,
                document_type=document_type,
                relative_path=path,
                content_type=content_type,
                size_bytes=len(content),
                uploaded_by=user,
                uploaded_by_name=user_name,
            )
    except BaseException:
        storage.delete_quietly(path)
        raise

    record_event(
        "document.uploaded",
        actor=user,
        target=document,
        metadata={"application": str(application.id), "type": document_type},
    )
    return document


def missing_documents(application) -> dict:
    """Returns {"documents.<type>": message} for submit validation."""
    present = set(
        Document.objects.filter(application=application, is_current=True).values_list(
            "document_type", flat=True
        )
    )
    errors = {
        f"documents.{kind.value}": f"{kind.label} is required."
        for kind in REQUIRED_DOCUMENTS
        if kind.value not in present
    }
    if not present & {kind.value for kind in SIGNATURE_DOCUMENTS}:
        errors["documents.member_signature"] = "A signature or thumbprint is required."
    return errors


def set_staff_signature(membership, *, raw, actor) -> StaffSignature:
    content, _ = images.normalize_signature(raw)
    path = storage.signature_file_path(membership)
    storage.write(path, content)

    try:
        with transaction.atomic():
            StaffSignature.objects.filter(membership=membership, is_current=True).update(
                is_current=False
            )
            signature = StaffSignature.objects.create(
                membership=membership, relative_path=path, uploaded_by=actor
            )
    except BaseException:
        storage.delete_quietly(path)
        raise

    record_event("signature.updated", actor=actor, target=membership)
    return signature


def current_signature(membership) -> StaffSignature | None:
    return StaffSignature.objects.filter(membership=membership, is_current=True).first()


def _forget_photo(path: str) -> None:
    if path:
        transaction.on_commit(lambda: storage.delete_quietly(path))


def set_staff_photo(membership, *, raw: bytes, actor) -> None:
    content = images.normalize_photo(raw)
    path = storage.photo_file_path(membership)
    storage.write_public(path, content)

    previous = membership.photo_path
    membership.photo_path = path
    try:
        membership.save(update_fields=["photo_path", "updated_at"])
    except BaseException:
        storage.delete_quietly(path)
        raise
    _forget_photo(previous)
    record_event("staff.photo_updated", actor=actor, target=membership)


def remove_staff_photo(membership, *, actor) -> None:
    previous = membership.photo_path
    if not previous:
        return
    membership.photo_path = ""
    membership.save(update_fields=["photo_path", "updated_at"])
    _forget_photo(previous)
    record_event("staff.photo_removed", actor=actor, target=membership)


# Their own signature goes on the printed form. Other approvers sign through their head.
OWN_SIGNATURE_PERMISSIONS = {"applications.submit", "applications.approve_am"}


def needs_signature(membership, permissions=None) -> bool:
    from apps.applications.models import Signatory
    from apps.rbac.services import permissions_for

    held = permissions if permissions is not None else permissions_for(membership)
    if OWN_SIGNATURE_PERMISSIONS & set(held):
        return True
    return Signatory.objects.filter(membership=membership).exists()
