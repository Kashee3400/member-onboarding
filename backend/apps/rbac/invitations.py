import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.audit.services import record_event
from apps.notifications.tasks import send_invitation

from .models import StaffInvitation

VALID_FOR = timedelta(days=7)
NOT_VALID = "This invitation link is not valid any more. Ask your administrator for a new one."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_pending(membership) -> bool:
    """Invited, and the password still not chosen."""
    return not membership.user.has_usable_password()


def invite(membership, *, actor) -> str:
    """A fresh link, which also ends any earlier one. Returns the link."""
    if not is_pending(membership):
        raise exceptions.ValidationError(
            {"invitation": ["This person has already set up their account."]}
        )
    now = timezone.now()
    StaffInvitation.objects.filter(
        membership=membership, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now, updated_at=now)

    token = secrets.token_urlsafe(32)
    StaffInvitation.objects.create(
        membership=membership,
        token_hash=_hash(token),
        expires_at=now + VALID_FOR,
        invited_by=actor,
    )
    organization = membership.organization
    link = f"{settings.PORTAL_URL}/accept-invite?organization={organization.slug}&token={token}"
    user = membership.user
    transaction.on_commit(
        lambda: send_invitation.delay(
            str(organization.id),
            user.email,
            user.full_name or user.email,
            organization.name,
            actor.full_name or actor.email,
            link,
        )
    )
    record_event("staff.invited", actor=actor, target=membership)
    return link


def open_invitation(token: str) -> StaffInvitation:
    found = (
        StaffInvitation.objects.select_related("membership__user", "membership__organization")
        .filter(token_hash=_hash(token or ""))
        .first()
    )
    if (
        found is None
        or found.accepted_at
        or found.revoked_at
        or found.expires_at < timezone.now()
        or not found.membership.is_active
        or not is_pending(found.membership)
    ):
        raise exceptions.NotFound(NOT_VALID)
    return found


@transaction.atomic
def accept(token: str, *, password: str, full_name: str):
    invitation = open_invitation(token)
    user = invitation.membership.user
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise exceptions.ValidationError({"password": exc.messages}) from exc

    user.set_password(password)
    user.must_change_password = False
    user.full_name = full_name.strip() or user.full_name
    user.save(update_fields=["password", "must_change_password", "full_name", "updated_at"])
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at", "updated_at"])
    record_event("staff.invitation_accepted", actor=user, target=invitation.membership)
    return user
