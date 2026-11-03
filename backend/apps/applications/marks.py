"""
Fields a reviewer marks wrong while reading a form, each with a short reason. They
are kept per submission and per person, so they survive a reload and others on the
stage see them, and a rejection carries them to the facilitator.
"""

from rest_framework import exceptions

from apps.audit.services import record_event
from apps.core.exceptions import Conflict
from apps.rbac.catalog import APPROVE_ALL

from . import review_settings, review_steps, services
from .models import FieldMark


def _ensure_reviewer(application, user) -> None:
    """The same people who could reject the form now."""
    permission = review_steps.STAGE_PERMISSIONS.get(application.status)
    if permission is None:
        raise Conflict("Fields are marked while the form waits for review.")
    held = user.active_permissions
    if permission not in held and APPROVE_ALL not in held:
        raise exceptions.PermissionDenied("This stage needs a different role.")
    services.ensure_not_preparer(application, user)


def current(application):
    return FieldMark.objects.filter(
        application=application, revision=application.revision
    ).order_by("created_at")


def serialized(application, user) -> list[dict]:
    admin = APPROVE_ALL in user.active_permissions
    return [
        {
            "id": mark.id,
            "path": mark.path,
            "label": review_settings.field_label(mark.path),
            "reason": mark.reason,
            "marked_by_name": mark.marked_by_name,
            "marked_at": mark.updated_at,
            "mine": mark.marked_by_id == user.pk,
            "can_remove": admin or mark.marked_by_id == user.pk,
        }
        for mark in current(application)
    ]


def mark(application, *, user, path: str, reason: str) -> FieldMark:
    """Marking a field again changes the reason: one mark per field and person."""
    _ensure_reviewer(application, user)
    if path not in review_settings.MARKABLE:
        raise exceptions.ValidationError({"path": ["This is not a field on the form."]})
    if path.split(".")[0] not in review_steps.my_sections(user.active_membership):
        raise exceptions.ValidationError({"path": ["You can mark fields only on your own steps."]})

    found, created = FieldMark.objects.update_or_create(
        application=application,
        revision=application.revision,
        path=path,
        marked_by=user,
        defaults={"reason": reason.strip(), "marked_by_name": services.display_name(user)},
    )
    record_event(
        "application.field_marked",
        actor=user,
        target=application,
        metadata={"revision": application.revision, "path": path, "changed": not created},
    )
    return found


def unmark(application, *, user, mark_id) -> None:
    _ensure_reviewer(application, user)
    found = current(application).filter(pk=mark_id).first()
    if found is None:
        raise exceptions.NotFound("This mark is gone.")
    if found.marked_by_id != user.pk and APPROVE_ALL not in user.active_permissions:
        raise exceptions.PermissionDenied("Only who marked it can remove it.")
    found.delete()
    record_event(
        "application.field_unmarked",
        actor=user,
        target=application,
        metadata={"revision": application.revision, "path": found.path},
    )
